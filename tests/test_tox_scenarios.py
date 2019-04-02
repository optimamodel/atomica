"""
Check whether automated model documentation template generation works
"""

import atomica as at
import numpy as np

def test_program_scenarios():

    P = at.demo('tb',do_run=False)

    # Get the default values for coverage etc.
    instructions = at.ProgramInstructions(2018)
    res_baseline = P.run_sim(result_name='Baseline',parset='default',progset='default',progset_instructions=instructions)

    alloc = res_baseline.get_alloc(2018)
    capacity = res_baseline.get_coverage('capacity',2018)
    coverage = res_baseline.get_coverage('fraction',2018)

    # Run a budget scenario manually
    doubled_budget = {x: v * 2 for x, v in alloc.items()}
    instructions = at.ProgramInstructions(2018,alloc=doubled_budget)
    res_doubled = P.run_sim(result_name='Doubled budget',parset='default',progset='default',progset_instructions=instructions)

    # Compare spending in 2018
    d = at.PlotData.programs([res_baseline, res_doubled],quantity='spending')
    d.interpolate(2018)
    at.plot_bars(d,stack_outputs='all')

    # Run a capacity scenario manually
    doubled_capacity = {x: v * 2 for x, v in capacity.items()}
    instructions = at.ProgramInstructions(2018,capacity=doubled_capacity)
    res_capacity = P.run_sim(result_name='Doubled capacity',parset='default',progset='default',progset_instructions=instructions)

    # # Compare capacity in 2018
    d = at.PlotData.programs([res_baseline, res_capacity],quantity='coverage_capacity')
    d.interpolate(2018)
    at.plot_bars(d,stack_outputs='all')

    # Run a coverage scenario manually
    doubled_coverage = {x: v * 2 for x, v in coverage.items()}
    instructions = at.ProgramInstructions(2018,coverage=doubled_coverage)
    res_coverage = P.run_sim(result_name='Doubled coverage',parset='default',progset='default',progset_instructions=instructions)

    # Compare coverage in 2018 - notice how the output coverage is capped to 1.0
    # even though the instructions contain fractional coverage values >1.0
    d = at.PlotData.programs([res_baseline, res_coverage],quantity='coverage_fraction')
    d.interpolate(2018)
    at.plot_bars(d,stack_outputs='all')

    # Compare program outcomes (incidence from 2018-2023)
    # Note that the doubled capacity scenario here is basically the same as
    # the doubled budget scenario because there were no capacity constraints
    # (the main use case for running a capacity scenario would be to
    # investigate circumventing capacity constraints).
    # On the other hand, the coverage scenario has fixed coverage from 2018-2023 whereas
    # the other scenarios have variable coverage, which is why the coverage scenario has
    # a different outcome
    d = at.PlotData([res_baseline, res_doubled,res_capacity,res_coverage],outputs=':acj',pops='total',t_bins=[2018,2023])
    # Show change in incidence relative to baseline to improve clarity in this plot
    baseline = d.series[0].vals[0]
    for s in d.series:
        s.vals -= baseline
    at.plot_bars(d)

    # Run a budget scenario via the actual scenario infrastructure
    scen = at.BudgetScenario(name='Doubled budget scenario', alloc=doubled_budget, start_year=2018)
    res_doubled_scen = scen.run(P, parset='default', progset='default')

    # Run a coverage scenario via the scenario infrastructure
    scen = at.CoverageScenario(name='Double coverage scenario', coverage=doubled_coverage, start_year=2018)
    res_coverage_scen = scen.run(P, parset='default', progset='default')

    # Check that the infrastructure gives the same result as direct instructions and
    # also that the budget and coverage scenarios give different results
    d = at.PlotData([res_doubled,res_doubled_scen, res_coverage,res_coverage_scen],outputs=':acj',pops='total',t_bins=[2018,2023])
    at.plot_bars(d)

def test_timevarying_progscen():
    # This test demonstrates doing time-varying overwrites
    # The example below shows how you can pass in a TimeSeries
    # instead of a scalar in the dict of overwrites. Although shown
    # for coverage below, this same approach works for alloc/budget
    # and capacity scenarios as well

    P = at.demo('sir',do_run=False)
    instructions = at.ProgramInstructions(2018)
    res_baseline = P.run_sim(result_name='Baseline',parset='default',progset='default',progset_instructions=instructions)

    coverage = {
        'Risk avoidance':0.5,
         'Harm reduction 1':0.25,
         'Harm reduction 2':at.TimeSeries([2018,2020],[0.7,0.2]),
    }
    scen = at.CoverageScenario('Reduced coverage','default','default',coverage=coverage,start_year=2018)
    scen_result = scen.run(project=P)
    d = at.PlotData.programs([res_baseline,scen_result],quantity='coverage_fraction')
    at.plot_series(d)

def test_parameter_scenarios():

    proj = at.demo('sir',do_run=False)
    proj.settings.update_time_vector(start=2000,end=2023)

    # Check that it runs with an empty scvalues
    scvalues = dict()
    scen = proj.make_scenario(which='parameter', name="No overwrites", instructions=scvalues)
    scen_results = scen.run(proj, proj.parsets["default"])

    # Check that it runs with a single overwrite
    scen_par = "contacts"
    scen_pop = "adults"
    scvalues[scen_par] = dict()
    scvalues[scen_par][scen_pop] = dict()
    scvalues[scen_par][scen_pop]["y"] = [80., 40]
    scvalues[scen_par][scen_pop]["t"] = [2010., 2020.]
    scen = proj.make_scenario(which='parameter', name="Increased deaths", instructions=scvalues)
    scen_results = scen.run(proj, proj.parsets["default"])

    # Check that default is stepped interpolation
    var = scen_results.get_variable('adults','contacts')[0]
    assert np.allclose(var.vals[var.t==2010][0], 80, equal_nan=True)  # Default tolerances are rtol=1e-05, atol=1e-08
    assert np.allclose(var.vals[var.t==2015][0], 80, equal_nan=True)  # Default tolerances are rtol=1e-05, atol=1e-08
    assert np.allclose(var.vals[var.t==2020][0], 40, equal_nan=True)  # Default tolerances are rtol=1e-05, atol=1e-08

    # Check smooth onset when smooth onset is applied
    scvalues[scen_par][scen_pop]["smooth_onset"] = 2
    scen = proj.make_scenario(which='parameter', name="Increased deaths", instructions=scvalues)
    scen_results = scen.run(proj, proj.parsets["default"])
    var = scen_results.get_variable('adults','contacts')[0]
    assert np.allclose(var.vals[var.t == 2018][0], 80, equal_nan=True)  # Default tolerances are rtol=1e-05, atol=1e-08
    assert np.allclose(var.vals[var.t == 2019][0], 60, equal_nan=True)  # Default tolerances are rtol=1e-05, atol=1e-08
    assert np.allclose(var.vals[var.t == 2020][0], 40, equal_nan=True)  # Default tolerances are rtol=1e-05, atol=1e-08

    # Check smooth onset works if larger than the gap in overwrite
    scvalues[scen_par][scen_pop]["smooth_onset"] = 11
    scen = proj.make_scenario(which='parameter', name="Increased deaths", instructions=scvalues)
    scen_results = scen.run(proj, proj.parsets["default"])
    var = scen_results.get_variable('adults','contacts')[0]
    assert np.allclose(var.vals[var.t == 2010][0], 80, equal_nan=True)  # Default tolerances are rtol=1e-05, atol=1e-08
    assert np.allclose(var.vals[var.t == 2015][0], 60, equal_nan=True)  # Default tolerances are rtol=1e-05, atol=1e-08
    assert np.allclose(var.vals[var.t == 2020][0], 40, equal_nan=True)  # Default tolerances are rtol=1e-05, atol=1e-08

    # Check that multiple overwrites work
    scen_par = "transpercontact"
    scen_pop = "adults"
    scvalues[scen_par] = dict()
    scvalues[scen_par][scen_pop] = dict()
    scvalues[scen_par][scen_pop]["y"] = [0.008, 0.005]
    scvalues[scen_par][scen_pop]["t"] = [2010., 2020.]
    scen = proj.make_scenario(which='parameter', name="Increased deaths", instructions=scvalues)
    scen_results = scen.run(proj, proj.parsets["default"])
    var1 = scen_results.get_variable('adults','contacts')[0]
    var2 = scen_results.get_variable('adults','transpercontact')[0]

    assert np.allclose(var1.vals[var1.t == 2010][0], 80, equal_nan=True)  # Default tolerances are rtol=1e-05, atol=1e-08
    assert np.allclose(var1.vals[var1.t == 2015][0], 60, equal_nan=True)  # Default tolerances are rtol=1e-05, atol=1e-08
    assert np.allclose(var1.vals[var1.t == 2020][0], 40, equal_nan=True)  # Default tolerances are rtol=1e-05, atol=1e-08
    assert np.allclose(var2.vals[var2.t == 2010][0], 0.008, equal_nan=True)  # Default tolerances are rtol=1e-05, atol=1e-08
    assert np.allclose(var2.vals[var2.t == 2015][0], 0.008, equal_nan=True)  # Default tolerances are rtol=1e-05, atol=1e-08
    assert np.allclose(var2.vals[var2.t == 2020][0], 0.005, equal_nan=True)  # Default tolerances are rtol=1e-05, atol=1e-08


if __name__ == '__main__':
    test_program_scenarios()
    test_timevarying_progscen()
    test_parameter_scenarios()
