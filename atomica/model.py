# %% Imports

from atomica.system import AtomicaException, logger # CK: warning, should relabel exception
from atomica.structure_settings import FrameworkSettings as FS
from atomica.structure import convertQuantity
#from optima_tb.validation import checkTransitionFraction # CK: warning, should not import optima_tb!!
#import optima_tb.settings as project_settings
from atomica.results import Result
from atomica.parser_function import FunctionParser
#from optima_tb.ModelPrograms import ModelProgramSet, ModelProgram
from collections import defaultdict # CK: warning, should probably remove
from sciris.core import odict, uuid

parser = FunctionParser(debug=False)  # Decomposes and evaluates functions written as strings, in accordance with a grammar defined within the parser object.

import pickle
import numpy as np
from copy import deepcopy as dcp
import matplotlib.pyplot as plt

# TODO: Put this in a better place.
TOLERANCE = 1e-6

class Variable(object):
    '''
    Lightweight abstract class to store a variable array of values (presumably corresponding to an external time vector).
    Includes an attribute to describe the format of these values.
    Examples include characteristics and dependent parameters (NB. all non-dependents parameter correspond to links)
    '''
    def __init__(self, name='default'):
        self.uid = uuid()
        self.name = name
        self.t = None
        self.dt = None
        if 'vals' not in dir(self): # characteristics already have a vals method
            self.vals = None
        self.units = 'unknown'              # 'unknown' units are distinct to dimensionless units, that have value ''

    def preallocate(self,tvec,dt):
        self.t = tvec
        self.dt = dt
        self.vals = np.ones(tvec.shape) * np.nan

    def plot(self):
        plt.figure()
        plt.plot(self.t,self.vals,label=self.name)
        plt.legend()
        plt.xlabel('Year')
        plt.ylabel("%s (%s)" % (self.name,self.units))

    def update(self,ti=None):
        # A Variable can have a function to update its value at a given time, which is
        # overloaded differently for Characteristics and Parameters
        return

    def set_dependent(self):
        # Make the variable a dependency. For Compartments and Links, this does nothing. For Characteristics and
        # Parameters, it will set the dependent flag, but in addition, any validation constraints e.g. a Parameter
        # that depends on Links cannot itself be a dependency, will be enforced
        return

    def __repr__(self):
        return '%s "%s" (%s)' % (self.__class__.__name__,self.name,self.uid)

class Compartment(Variable):
    ''' A class to wrap up data for one compartment within a cascade network. '''

    def __init__(self, name='default'):
        Variable.__init__(self, name=name)
        self.units = 'people'
        self.tag_birth = False                      # Tag for whether this compartment contains unborn people.
        self.tag_dead = False                       # Tag for whether this compartment contains dead people.
        self.is_junction = False
        self.vals = None

        self.outlinks = []
        self.inlinks = []

    def unlink(self):
        self.outlinks = [x.uid for x in self.outlinks]
        self.inlinks = [x.uid for x in self.inlinks]

    def relink(self,objs):
        self.outlinks = [objs[x] for x in self.outlinks]
        self.inlinks = [objs[x] for x in self.inlinks]

    def expected_duration(self,ti=None):
        # Returns the expected number of years that an individual is expected to remain
        # in this compartment for, if the outgoing flow rates are maintained
        if ti is None:
            ti = np.arange(0,len(self.t))

        outflow_probability = 0
        for link in self.outlinks:
            if link.parameter.units == 'fraction':
                outflow_probability += 1 - (1 - link.parameter.vals[ti]) ** self.dt  # A formula for converting from yearly fraction values to the dt equivalent.
            elif link.parameter.units == 'number':
                outflow_probability += link.parameter.vals[ti]*dt/self.vals[ti]
            else:
                raise OptimaException('Unknown parameter units')

        remain_probability = 1-outflow_probability
        dur = np.zeros(outflow_probability.shape)
        # From OSL/HMM-MAR:
        # Given a transition probability, what is the expected lifetime in units of steps?
        # This can be determined using a symbolic integration, below
        # syms k_step p;
        # assume(p>0);
        # f =(k_step)*p^k_step*(1-p); # (probability that the state lasts k *more* steps, multiplied by lifetime which is k)
        # fa = 1+int(f,k_step,0,inf); # Add 1 to the lifetime because all states last at least 1 sample
        # f = @(x) double(subs(fa,p,x));
        #
        # However, the result of the symbolic integration contains a limit which is
        # zero unless p=1, but p=1 is not needed because we know it means the compartment immediately empties.
        # So instead of the function above, can instead drop the limit term and write the rest of the
        # expression out which gives identical results from p=0.00001 to p=0.99 (note that if dirichletdiag>=1)
        # then the upper bound on the transition probability is p=0.5 anyway for K=2
        dur[dur<1] = (1 - (1. / np.log(remain_probability[dur<1])**2)*(remain_probability[dur<1] - 1))*self.dt
        return dur

    def expected_outflow(self,ti):
        # After 1 year, where are people expected to be? If people would leave in less than a year,
        # then the numbers correspond to when the compartment is empty
        popsize = self.vals[ti] # This is the number of people who are leaving

        outflow = {link.dest.name: popsize * link.vals[ti]/self.dt for link in self.outlinks}
        rescale = popsize/sum([y for _,y in outflow.items()])
        for x in outflow.keys():
            outflow[x] *= rescale
        outflow[self.name] = popsize - sum([y for _,y in outflow.items()])

        return outflow

class Characteristic(Variable):
    ''' A characteristic represents a grouping of compartments 
    '''
    def __init__(self, name='default'):
        # includes is a list of Compartments, whose values are summed
        # the denominator is another Characteristic that normalizes this one
        # All passed by reference so minimal performance impact
        Variable.__init__(self, name=name)
        self.units = 'people'
        self.includes = []
        self.denominator = None
        self.dependency = False # This flag indicates whether another variable depends on this one, indicating the value needs to be computed during integration
        self.internal_vals = None

    def preallocate(self,tvec,dt):
        # Note that we don't use Variable.preallocate() here because we cannot
        # preallocate self.vals because it is a property method
        self.t = tvec
        self.dt = dt
        self.internal_vals = np.ones(tvec.shape) * np.nan

    @property
    def vals(self):
        if self.internal_vals is None:
            vals = np.zeros(self.t.shape)

            for comp in self.includes:
                vals += comp.vals

            if self.denominator is not None:
                denom = self.denominator.vals
                vals_zero = vals < TOLERANCE
                vals[denom > 0] /= denom[denom > 0]
                vals[vals_zero] = 0.0
                vals[(denom<=0) & (~vals_zero)] = np.inf

            return vals
        else:
            return self.internal_vals


    def set_dependent(self):
        self.dependency = True

    def unlink(self):
        self.includes = [x.uid for x in self.includes]
        self.denominator = self.denominator.uid if self.denominator is not None else None

    def relink(self,objs):
        # Given a dictionary of objects, restore the internal references
        # based on the UUID
        self.includes = [objs[x] for x in self.includes]
        self.denominator = objs[self.denominator] if self.denominator is not None else None

    def add_include(self,x):
        assert isinstance(x,Compartment) or isinstance(x,Characteristic)
        self.includes.append(x)
        x.set_dependent()

    def add_denom(self,x):
        assert isinstance(x,Compartment) or isinstance(x,Characteristic)
        self.denominator = x
        x.set_dependent()
        self.units = ''

    def update(self,ti):
        self.internal_vals[ti] = 0
        for comp in self.includes:
            self.internal_vals[ti] += comp.vals[ti]
        if self.denominator is not None:
            denom  = self.denominator.vals[ti]
            if denom > 0:
                self.internal_vals[ti] /= denom
            elif self.internal_vals[ti] < TOLERANCE:
                self.internal_vals[ti] = 0  # Given a zero/zero case, make the answer zero.
            else:
                self.internal_vals[ti] = np.inf  # Given a non-zero/zero case, keep the answer infinite.

class Parameter(Variable):
    # A parameter is a Variable that can have a value computed via an f_stack and a list of 
    # dependent Variables. This class may need to be relabeld to avoid confusion with
    # the class in Parameter.py which provides a means of computing the Parameter that is used by the model.
    # This is a Parameter in the cascade.xlsx sense - there is one Parameter object for every item in the 
    # Parameters sheet. A parameter that maps to multiple transitions (e.g. doth_rate) will have one parameter
    # and multiple Link instances that depend on the same Parameter instance
    #
    #  *** Parameter values are always annualized ***
    def __init__(self, name='default'):
        Variable.__init__(self, name=name)
        self.vals = None
        self.deps = None
        self.f_stack = None
        self.limits = None # Can be a two element vector [min,max]
        self.dependency = False 
        self.scale_factor = 1.0
        self.links = [] # References to links that derive from this parameter
        self.source_popsize_cache_time = None
        self.source_popsize_cache_val = None

    def set_f_stack(self,f_stack,deps):
        self.f_stack = f_stack
        self.deps = deps

        # If this Parameter has links, it must be marked as dependent for evaluation during integration
        if self.links:
            self.set_dependent()


    def set_dependent(self):
        self.dependency = True
        if self.deps is not None: # Make all dependencies dependent too, this will propagate through dependent parameters
            for dep in self.deps:
                if isinstance(dep,Link):
                    raise OptimaException('A Parameter that depends on transition flow rates cannot be a dependency, it must be output only')
                dep.set_dependent()

    def unlink(self):
        self.links = [x.uid for x in self.links]
        self.deps = [x.uid for x in self.deps] if self.deps is not None else None

    def relink(self,objs):
        # Given a dictionary of objects, restore the internal references
        # based on the UUID
        self.links = [objs[x] for x in self.links]
        self.deps = [objs[x] for x in self.deps] if self.deps is not None else None

    def constrain(self,ti):
        # NB. Must be an array, so ti must must not be supplied
        if self.limits is not None:
            self.vals[ti] = max(self.limits[0],self.vals[ti])
            self.vals[ti] = min(self.limits[1],self.vals[ti])

    def update(self,ti=None):
        # Update the value of this Parameter at time index ti
        # by evaluating its f_stack function using the 
        # current values of all dependent variables at time index ti
        if ti is None:
            ti = np.arange(0,self.vals.size) # This corresponds to every time point
        else:
            ti = np.array(ti)

        if self.f_stack is None:
            return

        dep_vals = defaultdict(np.float64)
        for dep in self.deps:
            if isinstance(dep,Link):
                dep_vals[dep.name] += dep.vals[[ti]]/dep.dt
            else:
                dep_vals[dep.name] += dep.vals[[ti]]
        self.vals[ti] = parser.evaluateStack(stack=self.f_stack[0:], deps=dep_vals)   # self.f_stack[0:] makes a copy

    def source_popsize(self,ti):
        # Get the total number of people covered by this program
        # i.e. the sum of the source compartments of all links that
        # derive from this program
        # If impact_names is specified, it must be a list of link names
        # Then only links whose name is in that list will be included
        if ti == self.source_popsize_cache_time:
            return self.source_popsize_cache_val
        else:
            n = 0
            for link in self.links:
                n += link.source.vals[ti]
            self.source_popsize_cache_time = ti
            self.source_popsize_cache_val = n
            return n

class Link(Variable):
    '''
    A Link is a Variable that maps to a transition between compartments. As
    such, it contains an inflow and outflow compartment.  A Link's value is
    drawn from a Parameter, and there may be multiple links that draw values
    from the same parameter. The values stored in this extended version of
    Variable refer to flow rates. If used in ModelPop, the Link references two
    cascade compartments within a single population.
    '''
    #
    # *** Link values are always dt-based ***
    def __init__(self, parameter, object_from, object_to,tag,is_transfer=False):
        # Note that the Link's name is the transition tag
        Variable.__init__(self, name=tag)
        self.vals = None
        self.tag = tag
        self.units = 'people'

        self.parameter = parameter # Source parameter where the unscaled link value is drawn from (a single parameter may have multiple links)
        self.parameter.dependency = True # A transition parameter must be updated during integration

        self.source = object_from # Compartment to remove people from
        self.dest = object_to # Compartment to add people to

        # Wire up references to this object
        self.parameter.links.append(self)
        self.source.outlinks.append(self)
        self.dest.inlinks.append(self)

        self.is_transfer = is_transfer # A transfer connections compartments across populations

    def unlink(self):
        self.parameter = self.parameter.uid
        self.source = self.source.uid
        self.dest = self.dest.uid

    def relink(self,objs):
        # Given a dictionary of objects, restore the internal references
        # based on the UUID
        self.parameter = objs[self.parameter]
        self.source = objs[self.source]
        self.dest = objs[self.dest]

    def __repr__(self, *args, **kwargs):
        return "Link %s (parameter %s) - %s to %s" % (self.name, self.parameter.name, self.source.name, self.dest.name)

    def plot(self):
        Variable.plot(self)
        plt.title('Link %s to %s' % (self.source.name,self.dest.name))

# %% Cascade compartment and population classes
class Population(object):
    '''
    A class to wrap up data for one population within model.
    Each model population must contain a set of compartments with equivalent names.
    '''

    def __init__(self, framework, name='default'):
        self.uid = uuid()
        self.name = name          # Reference name for this object.

        self.comps = list()         # List of cascade compartments that this model population subdivides into.
        self.characs = list()       # List of output characteristics and parameters (dependencies computed during integration, pure outputs added after)
        self.links = list()         # List of intra-population cascade transitions within this model population.
        self.pars = list()
        
        self.comp_lookup = dict()      # Maps name of a compartment to a compartment
        self.charac_lookup = dict()
        self.par_lookup= dict()
        self.link_lookup = dict() # Map name of Link to a list of Links with that name

        self.genCascade(framework=framework)    # Convert compartmental cascade into lists of compartment and link objects.

        self.popsize_cache_time = None
        self.popsize_cache_val = None

    def __repr__(self):
        return '%s "%s" (%s)' % (self.__class__.__name__,self.name,self.uid)

    def unlink(self):
        for obj in self.comps + self.characs + self.pars + self.links:
            obj.unlink()
        self.comp_lookup = None
        self.charac_lookup = None
        self.par_lookup = None
        self.link_lookup = None

    def relink(self,objs):
        for obj in self.comps + self.characs + self.pars + self.links:
            obj.relink(objs)
        self.comp_lookup = {comp.name:comp for comp in self.comps}
        self.charac_lookup = {charac.name:charac for charac in self.characs}
        self.par_lookup = {par.name:par for par in self.pars}
        link_names = set([link.name for link in self.links])
        self.link_lookup = {name:[link for link in self.links if link.name == name] for name in link_names}

    def popsize(self,ti=None):
        # A population's popsize is the sum of all of the people in its compartments, excluding
        # birth and death compartments
        if ti is None:
            return np.sum([comp.vals for comp in self.comps if (not comp.tag_birth and not comp.tag_dead)],axis=0)

        if ti == self.popsize_cache_time:
            return self.popsize_cache_val
        else:
            n = 0
            for comp in self.comps:
                if not comp.tag_birth and not comp.tag_dead:
                    n += comp.vals[ti]

            return n

    def getVariable(self,name):
        # Returns a list of variables whose name matches the requested name
        # At the moment, names are unique across object types and within object
        # types except for links, but if that logic changes, simple modifications can
        # be made here
        if name in self.comp_lookup:
            return [self.comp_lookup[name]]
        elif name in self.charac_lookup:
            return [self.charac_lookup[name]]
        elif name in self.par_lookup:
            return [self.par_lookup[name]]
        elif name in self.link_lookup:
            return self.link_lookup[name]
        else:
            raise AtomicaException('Object %s not found' % (name))

    def getComp(self, comp_name):
        ''' Allow compartments to be retrieved by name rather than index. Returns a Compartment. '''
        return self.comp_lookup[comp_name]

    def getLinks(self, name):
        ''' Retrieve Links'''
        # Links can be looked up by parameter name or by link name, unlike getVariable. This is because
        # getLinks() is guaranteed to return a list of Link objects
        # As opposed to getVariable which would retrieve the Parameter for 'doth rate' and the Links for 'z'
        if name in self.par_lookup:
            return self.par_lookup[name].links
        elif name in self.link_lookup:
            return self.link_lookup[name]
        else:
            raise OptimaException('Object %s not found' % (name))

    def getCharac(self, charac_name):
        ''' Allow dependencies to be retrieved by name rather than index. Returns a Variable. '''
        return self.charac_lookup[charac_name]

    def getPar(self, par_name):
        ''' Allow dependencies to be retrieved by name rather than index. Returns a Variable. '''
        return self.par_lookup[par_name]

    def genCascade(self, framework):
        '''
        Generate a compartmental cascade as defined in a settings object.
        Fill out the compartment, transition and dependency lists within the model population object.
        Maintaining order as defined in a cascade workbook is crucial due to cross-referencing.
        '''

        # Instantiate Compartments
        for name in framework.specs[FS.KEY_COMPARTMENT]:
            spec = framework.getSpec(name)
            self.comps.append(Compartment(name=name))
            if spec["is_source"]:
                self.comps[-1].tag_birth = True
            if spec["is_sink"]:
                self.comps[-1].tag_dead = True
            if spec["is_junction"]:
                self.comps[-1].is_junction = True
        self.comp_lookup = {comp.name:comp for comp in self.comps}

        # Characteristics first pass, instantiate objects
        for name in framework.specs[FS.KEY_CHARACTERISTIC]:
            self.characs.append(Characteristic(name=name))
        self.charac_lookup = {charac.name:charac for charac in self.characs}

        # Characteristics second pass, add includes and denominator
        for name in framework.specs[FS.KEY_CHARACTERISTIC]:
            spec = framework.getSpec(name)
            charac = self.getCharac(name)
            for inc_name in spec["includes"]:
                charac.add_include(self.getVariable(inc_name)[0]) # nb. We expect to only get one match for the name, so use index 0
            if "denominator" in spec and not spec["denominator"] is None:
                charac.add_denom(self.getVariable(spec["denominator"])[0])

        # Parameters first pass, create parameter objects and links
        for name in framework.specs[FS.KEY_PARAMETER]:
            spec = framework.getSpec(name)
            par = Parameter(name=name)
            self.pars.append(par)
            if "links" in spec:
#                tag = settings.linkpar_specs[name]['tag']
                for pair in spec["links"]:
                    src = self.getComp(pair[0])
                    dst = self.getComp(pair[1])
# TODO!! ATOMICA - Need to find the link tag here
                    tag = src.name + '-' + dst.name     # Temporary tag solution.
                    new_link = Link(par,src,dst,tag) # The link needs to be named with the Parameter it derives from so that Results can find it later
                    if tag not in self.link_lookup:
                        self.link_lookup[tag] = [new_link]
                    else:
                        self.link_lookup[tag].append(new_link)
                    self.links.append(new_link)
        self.par_lookup = {par.name:par for par in self.pars}

        # Parameters second pass, process f_stacks, deps, and limits
        for name in framework.specs[FS.KEY_PARAMETER]:
            spec = framework.getSpec(name)
            par = self.getPar(name)

#            if ('min' in spec) or ('max' in spec):
#                par.limits = [-np.inf, np.inf]
#                if 'min' in spec:
#                    par.limits[0] = spec['min']
#                if 'max' in spec:
#                    par.limits[1] = spec['max']

            if not spec[FS.TERM_FUNCTION] is None:
                f_stack = dcp(spec[FS.TERM_FUNCTION])
                deps = []
                for dep_name in spec["dependencies"]:
                    deps += self.getVariable(dep_name)
                par.set_f_stack(f_stack,deps)

    def preallocate(self, tvec, dt):
        '''
        Pre-allocate variable arrays in compartments, links and dependent variables for faster processing.
        Array maintains initial value but pre-fills everything else with NaNs.
        Thus errors due to incorrect parset value saturation should be obvious from results.
        '''
        for obj in self.comps + self.characs + self.links + self.pars:
            obj.preallocate(tvec,dt)

    def initialize_compartments(self,parset,framework,t_init):
        # Given a set of characteristics and their initial values, compute the initial
        # values for the compartments by solving the set of characteristics simultaneously

        characs = [c for c in self.characs if framework.getSpecValue(c.name,"datapage_order")!=-1]
        characs += [c for c in self.comps if framework.getSpecValue(c.name,"datapage_order")!=-1]
#        print(characs)
        comps = [c for c in self.comps if not (c.tag_birth or c.tag_dead)]
        charac_indices = {c.name:i for i,c in enumerate(characs)} # Make lookup dict for characteristic indices
        comp_indices = {c.name:i for i,c in enumerate(comps)} # Make lookup dict for compartment indices

        b = np.zeros((len(characs),1))
        A = np.zeros((len(characs),len(comps)))

        def extract_includes(charac):
            includes = []
            for inc in charac.includes:
                if isinstance(inc,Characteristic):
                    includes += extract_includes(inc)
                else:
                    includes.append(inc)
            return includes

#        print([(c,framework.getSpecValue(c.name,"datapage_order")) for c in self.characs])
        # Construct the characteristic value vector (b) and the includes matrix (A)
        for i,c in enumerate(characs):
            # Look up the characteristic value
            par = parset.getPar(c.name)
            b[i] = par.interpolate(tvec=np.array([t_init]), pop_name=self.name)[0]
            # Run exception clauses for compartment logic.
            try:
                if c.denominator is not None:
                    denom_par = parset.pars['characs'][parset.par_ids['characs'][c.denominator.name]]
                    b[i] *= denom_par.interpolate(tvec=np.array([t_init]), pop_name=self.name)[0]
            except: pass
            try:
                for inc in extract_includes(c):
                    A[i,comp_indices[inc.name]] = 1.0
            except: A[i,comp_indices[c.name]] = 1.0

        # Solve the linear system
        x, residual, rank, _ = np.linalg.lstsq(A,b,rcond=-1)

        # Halt if the solution is not unique (could relax this check later)
        if rank < A.shape[1]:
            raise AtomicaException('Characteristics are not full rank, cannot determine a unique initialization')

        # Print warning for characteristics that are not well matched by the compartment size solution
        proposed = np.matmul(A,x)
        for i in range(0,len(characs)):
            if abs(proposed[i]-b[i]) > TOLERANCE:#project_settings.TOLERANCE:
                logger.warn('Characteristic %s %s - Requested %f, Calculated %f' % (self.name,characs[i].name,b[i],proposed[i]))
        
        # Print diagnostic output for compartments that were assigned a negative value
        def report_characteristic(charac,n_indent=0):
            if charac.name in charac_indices:
                logger.warn(n_indent * '\t' + 'Characteristic %s: Target value = %f' % (charac.name,b[charac_indices[charac.name]]))
            else:
                logger.warn(n_indent * '\t' + 'Characteristic %s not in databook: Target value = N/A (0.0)' % (charac.name))

            n_indent += 1
            for inc in charac.includes:
                if isinstance(inc,Characteristic):
                    report_characteristic(inc,n_indent)
                else:
                    logger.warn(n_indent * '\t' + 'Compartment %s: Computed value = %f' % (inc.name,x[comp_indices[inc.name]]))

        for i in range(0, len(comps)):
            if x[i] < -TOLERANCE:
                logger.warn('Compartment %s %s - Calculated %f' % (self.name, comps[i].name, x[i]))
                for charac in characs:
                    try:
                        if comps[i] in extract_includes(charac):
                            report_characteristic(charac)
                    except:
                        if comps[i] == charac: report_characteristic(charac)


        # Halt for an unsatisfactory overall solution (could relax this check later)
        if residual > TOLERANCE:
            print(x)
            raise AtomicaException('Residual was %f which is unacceptably large (should be < %f) - this points to a probable inconsistency in the initial values' % (residual,TOLERANCE))

        # Halt for any negative popsizes
        if np.any(x < -TOLERANCE):
            raise AtomicaException('Negative initial popsizes')

        # Otherwise, insert the values
        for i,c in enumerate(comps):
            c.vals[0] = max(0.0,x[i])

        for c in self.comps:
            if c.tag_dead:
                c.vals[0] = 0

# %% Model class
class Model(object):
    ''' A class to wrap up multiple populations within model and handle cross-population transitions. '''

    def __init__(self,settings, framework, parset, progset=None, options=None):

        self.pops = list()              # List of population groups that this model subdivides into.
        self.pop_ids = dict()           # Maps name of a population to its position index within populations list.
        self.contacts = dict()          # Maps interactions 'from' (i.e. a->b for [a][b]) and 'into' (i.e. a<-b for [a][b]) Populations, marking them with a weight.
        self.sim_settings = odict()
        self.t_index = 0                # Keeps track of array index for current timepoint data within all compartments.
        self.programs_active = None     # True or False depending on whether Programs will be used or not
        self.pset = None                # Instance of ModelProgramSet
        self.t = None
        self.dt = None
        self.uid = uuid()
        self.build(settings, framework, parset, progset, options)

    def unlink(self):
        # Break cycles when deepcopying or pickling by swapping them for UIDs
        # Primary storage is in the comps, links, and outputs properties

        # If we are already unlinked, do nothing
        if self.pars_by_pop is None:
            return

        for pop in self.pops:
            pop.unlink()
        if self.pset is not None:
            self.pset.unlink()
        self.pars_by_pop = None

    def relink(self):
        # Need to enumerate objects at Model level because transitions link across pops

        # If we are already linked, do nothing
        if self.pars_by_pop is not None:
            return

        objs = {}
        for pop in self.pops:
            for obj in pop.comps + pop.characs + pop.pars + pop.links:
                objs[obj.uid] = obj

        for pop in self.pops:
            pop.relink(objs)

        self.pars_by_pop = dict()
        for pop in self.pops:
            for par in pop.pars:
                if par.name in self.pars_by_pop:
                    self.pars_by_pop[par.name].append(par)
                else:
                    self.pars_by_pop[par.name] = [par]

        if self.pset is not None:
            self.pset.relink(objs)

    def __getstate__(self):
        self.unlink()
        d = pickle.dumps(self.__dict__, protocol=-1) # Pickling to string results in a copy
        self.relink() # Relink, otherwise the original object gets unlinked
        return d

    def __setstate__(self, d):
        self.__dict__ = pickle.loads(d)
        self.relink()

    def getPop(self, pop_name):
        ''' Allow model populations to be retrieved by name rather than index. '''
        pop_index = self.pop_ids[pop_name]
        return self.pops[pop_index]

    def build(self, settings, framework, parset, progset=None, options=None):
        ''' Build the full model. '''

        if options is None: options = dict()

        self.t = settings.makeTimeVector() # NB. returning a mutable variable in a class @property method returns a new object each time
        self.dt = settings.dt

        # self.sim_settings['impact_pars_not_func'] = []      # Program impact parameters that are not functions of other parameters and thus already marked for dynamic updating.
        #                                                     # This is only non-empty if a progset is being used in the model.
        # parser.debug = settings.parser_debug

        for k, pop_name in enumerate(parset.pop_names):
            self.pops.append(Population(framework=framework, name=pop_name))
            #TODO! Update preallocate case
            self.pops[-1].preallocate(self.t,self.dt)     # Memory is allocated, speeding up model. However, values are NaN so as to enforce proper parset value saturation.
            self.pop_ids[pop_name] = k
            self.pops[-1].initialize_compartments(parset, framework, self.t[0])

        self.contacts = dcp(parset.contacts)    # Simple propagation of interaction details from parset to model.

        # Propagating cascade parameter parset values into ModelPops. Handle both 'tagged' links and 'untagged' dependencies.
        for cascade_par in parset.pars['cascade']:
            for pop_name in parset.pop_names:
                pop = self.getPop(pop_name)
                par = pop.getPar(cascade_par.name) # Find the parameter with the requested name
                par.vals = cascade_par.interpolate(tvec=self.t, pop_name=pop_name)
                # par.scale_factor = cascade_par.y_factor[pop_name]
                if par.links:
                    par.units = cascade_par.y_format[pop_name]

        # Propagating transfer parameter parset values into Model object.
        # For each population pair, instantiate a Parameter with the values from the databook
        # For each compartment, instantiate a set of Links that all derive from that Parameter
        # NB. If a Program somehow targets the transfer parameter, those values will automatically
        for trans_type in parset.transfers:
            if parset.transfers[trans_type]:
                for pop_source in parset.transfers[trans_type]:

                    transfer_parameter = parset.transfers[trans_type][pop_source] # This contains the data for all of the destrination pops

                    pop = self.getPop(pop_source)


                    for pop_target in transfer_parameter.y:

                        # Create the parameter object for this link (shared across all compartments)
                        par_name = trans_type + '_' + pop_source + '_to_' + pop_target # e.g. 'aging_0-4_to_15-64'
                        par = Parameter(name=par_name)
                        par.preallocate(self.t,self.dt)
                        val = transfer_parameter.interpolate(tvec=self.t, pop_name=pop_target)
                        par.vals = val
                        par.scale_factor = transfer_parameter.y_factor[pop_target]
                        par.units = transfer_parameter.y_format[pop_target]
                        pop.pars.append(par)
                        pop.par_lookup[par_name] = par

                        target_pop_obj = self.getPop(pop_target)

                        for source in pop.comps:
                            if not (source.tag_birth or source.tag_dead or source.is_junction):
                                # Instantiate a link between corresponding compartments
                                dest = target_pop_obj.getComp(source.name) # Get the corresponding compartment
                                link_tag = par_name + '_' + source.name # e.g. 'aging_0-4_to_15-64_sus'
                                link = Link(par, source, dest, link_tag, is_transfer=True)
                                link.preallocate(self.t,self.dt)
                                pop.links.append(link)
                                if link.name in pop.link_lookup:
                                    pop.link_lookup[link.name].append(link)
                                else:
                                    pop.link_lookup[link.name] = [link]

        # # Make a lookup dict for programs
        self.pars_by_pop = {}
        for pop in self.pops:
            for par in pop.pars:
                if par.name in self.pars_by_pop:
                    self.pars_by_pop[par.name].append(par)
                else:
                    self.pars_by_pop[par.name] = [par]

        # Finally, prepare ModelProgramSet helper if programs are going to be used
        if 'progs_start' in options:
            if progset is not None:
                self.programs_active = True
                self.sim_settings['progs_start'] = options['progs_start']

                if 'progs_end' in options:
                    self.sim_settings['progs_end'] = options['progs_end']
                else:
                    self.sim_settings['progs_end'] = np.inf # Neverending programs
                if 'init_alloc' in options:
                    self.sim_settings['init_alloc'] = options['init_alloc']
                else: self.sim_settings['init_alloc'] = {}
                if 'constraints' in options:
                    self.sim_settings['constraints'] = options['constraints']
                else:
                    self.sim_settings['constraints'] = None
                if 'alloc_is_coverage' in options:
                    self.sim_settings['alloc_is_coverage'] = options['alloc_is_coverage']
                else: self.sim_settings['alloc_is_coverage'] = False
                if 'saturate_with_default_budgets' in options:
                    self.sim_settings['saturate_with_default_budgets'] = options['saturate_with_default_budgets']
                for impact_name in progset.impacts:
                    if impact_name not in settings.par_funcs:
                        self.sim_settings['impact_pars_not_func'].append(impact_name)

                self.pset = ModelProgramSet(progset,self.pops) # Make a ModelProgramSet wrapper
                self.pset.load_constraints(self.sim_settings['constraints'])
                alloc = self.pset.get_alloc(self.t,self.dt,self.sim_settings)[0]
                self.pset.update_cache(alloc,self.t,self.dt) # Perform precomputations

            else:
                raise AtomicaException('ERROR: A model run was initiated with instructions to activate programs, but no program set was passed to the model.')
        else:
            self.programs_active = False

#        # Make sure initially-filled junctions are processed and initial dependencies are calculated.
#        self.updateValues(framework=framework, do_special=False)     # Done first just in case junctions are dependent on characteristics.
#                                                                                                # No special rules are applied at this stage, otherwise calculations would be iterated twice before the first step forward.
#                                                                                                # NOTE: If junction outflows were to be tagged by special rules, initial calculations may be off. Return to this later and consider logic rigorously.
#        self.processJunctions(framework=framework)
        self.updateValues(framework=framework)


        # set up sim_settings for later use wrt population tags
        for tag in ["is_source", "is_sink", "is_junction"]:
            self.sim_settings[tag] = []
            for node_name in framework.specs[FS.KEY_COMPARTMENT]:
                if framework.getSpecValue(node_name, tag):
                    self.sim_settings[tag].append(node_name)

    def process(self, framework, progset,full_output):
        ''' 
        Run the full model.
        '''

        for t in self.t[1:]:
            self.stepForward(framework=framework, dt=self.dt)
#            self.processJunctions(framework=framework)
            self.updateValues(framework=framework)

        for pop in self.pops:
            [par.update() for par in pop.pars if not par.dependency] # Update any remaining parameters
            for charac in pop.characs:
                charac.internal_vals = None # Wipe out characteristic vals to save space

            if not full_output:
                for par in pop.pars:
                    if (not par.name in settings.linkpar_specs) or (not 'output' in settings.linkpar_specs[par.name]) or (settings.linkpar_specs[par.name] != 'y'):
                        par.vals = None
                        for link in par.links:
                            link.vals = None

    def stepForward(self, framework, dt=1.0):
        '''
        Evolve model characteristics by one timestep (defaulting as 1 year).
        Each application of this method writes calculated values to the next position in popsize arrays, regardless of dt.
        Thus the corresponding time vector associated with variable dt steps must be tracked externally.
        '''

        ti = self.t_index

        for pop in self.pops:
            for comp in pop.comps:
                comp.vals[ti+1] = comp.vals[ti]

        for pop in self.pops:

            for comp_source in pop.comps:

                if not comp_source.is_junction:  # Junctions collect inflows during this step. They do not process outflows here.

                    outlinks = comp_source.outlinks  # List of outgoing links
                    outflow = np.zeros(len(comp_source.outlinks))  # Outflow for each link # TODO - store in the link objects?

                    for i, link in enumerate(outlinks):

                        # Compute the number of people that are going out of each link
                        transition = link.parameter.vals[ti]

                        if transition == 0.0:
                            # Note that commands below are all multiplicative and thus can't map an initial value of 0.0 to anything
                            # other than a flow rate of 0, so we can abort early here
                            outflow[i] = 0.0
                            continue

#                        if link.parameter.scale_factor is not None and link.parameter.scale_factor != project_settings.DO_NOT_SCALE:  # scale factor should be available to be used
#                            transition *= link.parameter.scale_factor

#                        if link.parameter.units == 'fraction':
#                            # check if there are any violations, and if so, deal with them
#                        if transition > 1.:
#                            transition = checkTransitionFraction(transition, settings.validation)
#                        converted_frac = 1 - (1 - transition) ** dt  # A formula for converting from yearly fraction values to the dt equivalent.
#                        if link.source.tag_birth:
#                            n_alive = 0
#                            for p in self.pops:
#                                n_alive += p.popsize(ti)
#                            converted_amt = n_alive * converted_frac
#                        else:
#                            converted_amt = comp_source.vals[ti] * converted_frac
#                        elif link.parameter.units == 'number':
#                            converted_amt = transition * dt
#                            if link.is_transfer:
#                                transfer_rescale = comp_source.vals[ti] / pop.popsize(ti)
#                                converted_amt *= transfer_rescale
#                        else:
#                            raise AtomicaException('Unknown parameter units! NB. "proportion" links can only appear in junctions')

                        value = convertQuantity(value = transition, initial_type = link.parameter.units, 
                                                                    final_type = FS.QUANTITY_TYPE_NUMBER, 
                                                                    set_size = comp_source.vals[ti], dt = self.dt)

                        outflow[i] = value

                    # Prevent negative population by proportionately downscaling the outflow
                    # if there are insufficient people _currently_ in the compartment
                    # Rescaling is performed if the validation setting is 'avert', otherwise
                    # either a warning will be displayed or an error will be printed
                    if not comp_source.tag_birth and np.sum(outflow) > comp_source.vals[ti]:
                        validation_level = settings.validation['negative_population']

                        if validation_level == project_settings.VALIDATION_AVERT or validation_level == project_settings.VALIDATION_WARN:
                            outflow = outflow / np.sum(outflow) * comp_source.vals[ti]
                        else:
                            warning = "Negative value encountered for: (%s - %s) at ti=%g : popsize = %g, outflow = %g" % (pop.name,comp_source.name,ti,comp_source.vals[ti],sum(outflow))
                            if validation_level == project_settings.VALIDATION_ERROR:
                                raise AtomicaException(warning)
                            elif validation_level == project_settings.VALIDATION_WARN:
                                logger.warn(warning)

                    # Apply the flows to the compartments
                    for i, link in enumerate(outlinks):
                        link.dest.vals[ti+1] += outflow[i]
                        link.vals[ti] = outflow[i]

                    comp_source.vals[ti+1] -= np.sum(outflow)


        # Guard against populations becoming negative due to numerical artifacts
        for pop in self.pops:
            for comp in pop.comps:
                comp.vals[ti+1] = max(0,comp.vals[ti+1])

        # Update timestep index.
        self.t_index += 1

    def processJunctions(self, framework):
        '''
        For every compartment considered a junction, propagate the contents onwards until all junctions are empty.
        '''

        ti = self.t_index
        ti_link = ti - 1
        if ti_link < 0: 
            ti_link = ti    # For the case where junctions are processed immediately after model initialisation.

        review_required = True
        review_count = 0
        while review_required:
            review_count += 1
            review_required = False # Don't re-run unless a junction has refilled

            if review_count > settings.recursion_limit:
                raise AtomicaException('ERROR: Processing junctions (i.e. propagating contents onwards) for timestep %i is taking far too long. Infinite loop suspected.' % ti_link)

            for pop in self.pops:
                junctions = [comp for comp in pop.comps if comp.is_junction]

                for junc in junctions:

                    if review_count == 1:
                        for link in junc.outlinks:
                            link.vals[ti] = 0

                    # If the compartment is numerically empty, make it empty
                    if junc.vals[ti] <= TOLERANCE:   # Includes negative values.
                        junc.vals[ti] = 0
                    else:
                        current_size = junc.vals[ti]
                        denom_val = sum(link.parameter.vals[ti_link] for link in junc.outlinks) # This is the total fraction of people requested to leave, so outflows are scaled to the entire compartment size
                        if denom_val == 0:
                            raise AtomicaException('ERROR: Proportions for junction "%s" outflows sum to zero, resulting in a nonsensical ratio. There may even be (invalidly) no outgoing transitions for this junction.' % junction_name)
                        for link in junc.outlinks:
                            flow = current_size * link.parameter.vals[ti_link] / denom_val
                            link.source.vals[ti] -= flow
                            link.dest.vals[ti]   += flow
                            link.vals[ti] += flow
                            if link.dest.is_junction:
                                review_required = True # Need to review if a junction received an inflow at this step

    def updateValues(self, framework, do_special=True):
        '''
        Run through all parameters and characteristics flagged as dependencies for custom-function parameters and evaluate them for the current timestep.
        These dependencies must be calculated in the same order as defined in settings, characteristics before parameters, otherwise references may break.
        Also, parameters in the dependency list do not need to be calculated unless explicitly depending on another parameter.
        Parameters that have special rules are usually dependent on other population values, so are included here.
        '''

        ti = self.t_index

        # The output list maintains the order in which characteristics and parameters appear in the
        # settings, and also puts characteristics before parameters. So iterating through that list
        # will automatically compute them in the correct order

        # First, compute dependent characteristics, as parameters might depend on them
        for pop in self.pops:
            for charac in pop.characs:
                if charac.dependency:
                    charac.update(ti)
        
        # 1st:  Update parameters if they have an f_stack variable
        # 2nd:  Any parameter that is overwritten by a program-based cost-coverage-impact transformation.
        # 3rd:  Any parameter that is overwritten by a special rule, e.g. averaging across populations.
        # 4th:  Any parameter that is restricted within a range of values, i.e. by min/max values.
        # Looping through populations must be internal so that all values are calculated before special inter-population rules are applied.
        # We resolve one parameter at a time, in dependency order
        do_program_overwrite = self.programs_active and self.t[ti] >= self.sim_settings['progs_start'] and self.t[ti] <= self.sim_settings['progs_end']
        if do_program_overwrite:
            prog_vals = self.pset.compute_pars(ti)[0]

        for par_name in (framework.filter[FS.TERM_FUNCTION + FS.KEY_PARAMETER]):# + self.sim_settings['impact_pars_not_func']):
            pars = self.pars_by_pop[par_name] # All of the parameters with this name, across populations. There should be one for each population (these are Parameters, not Links)

            # First - update parameters that are dependencies, evaluating f_stack if required
            for par in pars:
                if par.dependency:
                    par.update(ti)

            # Then overwrite with program values
            if do_program_overwrite:
                for par in pars:
                    if par.uid in prog_vals:
                        par.vals[ti] = prog_vals[par.uid]

#            # Handle parameters tagged with special rules. Overwrite vals if necessary.
#            if do_special and 'rules' in settings.linkpar_specs[par_name]:
#                pars = self.pars_by_pop[par_name]  # All of the parameters with this name, across populations. There should be one for each population (these are Parameters, not Links)
#
#                old_vals = {par.uid: par.vals[ti] for par in self.pars_by_pop[par_name]}
#
#                rule = settings.linkpar_specs[par_name]['rules']
#                for pop in self.pops:
#                    if rule == 'avg_contacts_in':
#                        from_list = self.contacts['into'][pop.name].keys()
#
#                        # If interactions with a pop are initiated by the same pop, no need to proceed with special calculations. Else, carry on.
#                        if not ((len(from_list) == 1 and from_list[0] == pop.name)):
#
#                            if len(from_list) == 0:
#                                new_val = 0.0
#                            else:
#                                val_sum = 0.0
#                                weights = 0.0
#
#                                for k,from_pop in enumerate(from_list):
#                                    # All transition links with the same par_name are identically valued. For calculations, only one is needed for reference.
#                                    par = self.getPop(from_pop).getPar(par_name)
#                                    weight = self.contacts['into'][pop.name][from_pop]*self.getPop(from_pop).popsize(ti)
#                                    val_sum += old_vals[par.uid]*weight
#                                    weights += weight
#
#                                if abs(val_sum) > project_settings.TOLERANCE:
#                                    new_val = val_sum / weights
#                                else:
#                                    new_val = 0.0   # Only valid because if the weighted sum is zero, all pop_counts must be zero, meaning that the numerator is zero.
#
#                            # Update the parameter's value in this population - will propagate to links in next stage
#                            pop.getPar(par_name).vals[ti] = new_val

            # Restrict the parameter's value if a limiting range was defined
            for par in pars:
                par.constrain(ti)

    def calculateOutputs(self, framework):
        '''
        Calculate outputs (called cascade characteristics in settings).
        These outputs must be calculated in the same order as defined in settings, otherwise references may break.
        Include any parameters marked as an output in the cascade sheet.
        Return a dictionary with all of the outputs

        As outputs are all Variables or Characteristics they use the vals property for their value
        '''
        raise AtomicaException("This function should be deprecated because the Model will be the Results object")
        
        outputs = odict()

        for pop in self.pops:
            for output in pop.pars + pop.characs:
                if output.name not in outputs:
                    outputs[output.name] = odict()
                if pop.name in outputs[output.name]:
                    assert isinstance(output,Link), 'There is a duplicate output name that is NOT a link - this is not supposed to happen'
                    outputs[output.name][pop.name] += output.vals
                else:
                    outputs[output.name][pop.name] = output.vals
        return outputs



def runModel(settings, framework, parset, progset=None, options=None,full_output=True,name=None):
    '''
    Processes the TB epidemiological model.
    Parset-based overwrites are generally done externally, so the parset is only used for model-building.
    Progset-based overwrites take place internally and must be part of the processing step.
    The options dictionary is usually passed in with progset to specify when the overwrites take place.
    - If full_output = False, non-output Parameters (and corresponding links) will be set to None
    '''

    m = Model(settings, framework, parset, progset, options)
    m.process(framework, progset, full_output)
    return Result(model=m,parset=parset,name=name)
