/**
 * Utilities that are shared across pages
 */

import rpcs from '@/services/rpc-service'
import status from '@/services/status-service'

function sleep(time) {
  // Return a promise that resolves after _time_ milliseconds.
  return new Promise((resolve) => setTimeout(resolve, time));
}

function getUniqueName(fileName, otherNames) {
  let tryName = fileName
  let numAdded = 0
  while (otherNames.indexOf(tryName) > -1) {
    numAdded = numAdded + 1
    tryName = fileName + ' (' + numAdded + ')'
  }
  return tryName
}

function placeholders(vm, startVal) {
  var indices = []
  if (!startVal) {
    startVal = 0
  }
  for (var i = startVal; i <= 100; i++) {
    indices.push(i);
    vm.showGraphDivs[i] = false
    vm.showLegendDivs[i] = false
  }
  return indices;
}

function projectID(vm) {
  if (vm.$store.state.activeProject.project === undefined) {
    return ''
  }
  else {
    let projectID = vm.$store.state.activeProject.project.id
    return projectID
  }
}

function hasData(vm) {
  if (vm.$store.state.activeProject.project === undefined) {
    return false
  }
  else {
    return vm.$store.state.activeProject.project.hasData
  }
}

function hasPrograms(vm) {
  if (vm.$store.state.activeProject.project === undefined) {
    return false
  }
  else {
    return vm.$store.state.activeProject.project.hasPrograms
  }
}

function simStart(vm) {
  if (vm.$store.state.activeProject.project === undefined) {
    return ''
  }
  else {
    return vm.$store.state.activeProject.project.sim_start
  }
}

function simEnd(vm) {
  if (vm.$store.state.activeProject.project === undefined) {
    return ''
  }
  else {
    return vm.$store.state.activeProject.project.sim_end
  }
}

function simYears(vm) {
  if (vm.$store.state.activeProject.project === undefined) {
    return []
  }
  else {
    var sim_start = vm.$store.state.activeProject.project.sim_start
    var sim_end = vm.$store.state.activeProject.project.sim_end
    var years = []
    for (var i = sim_start; i <= sim_end; i++) {
      years.push(i);
    }
    console.log('sim years: ' + years)
    return years;
  }
}

function activePops(vm) {
  if (vm.$store.state.activeProject.project === undefined) {
    return ''
  }
  else {
    let pop_pairs = vm.$store.state.activeProject.project.pops
    let pop_list = ["All"]
    for(let i = 0; i < pop_pairs.length; ++i) {
      pop_list.push(pop_pairs[i][1]);
    }
    return pop_list
  }
}

function getPlotOptions(vm) {
  return new Promise((resolve, reject) => {
    console.log('getPlotOptions() called')
    status.start(vm) // Start indicating progress.
    let project_id = projectID(vm)
    rpcs.rpc('get_supported_plots', [project_id, true])
    .then(response => {
      vm.plotOptions = response.data // Get the parameter values
      status.succeed(vm, '')
      resolve(response)
    })
    .catch(error => {
      status.fail(vm, 'Could not get plot options: ' + error.message)
      reject(error)
    })          
  })
}

function makeGraphs(vm, graphdata) {
  let waitingtime = 0.5
  console.log('makeGraphs() called')
  status.start(vm) // Start indicating progress.
  vm.hasGraphs = true
  sleep(waitingtime * 1000)
  .then(response => {
    let n_plots = graphdata.length
    console.log('Rendering ' + n_plots + ' graphs')
    for (var index = 0; index <= n_plots; index++) {
      console.log('Rendering plot ' + index)
      var divlabel  = 'fig' + index

      var div  = document.getElementById(divlabel); // CK: Not sure if this is necessary? To ensure the div is clear first
      while (div.firstChild) {
        div.removeChild(div.firstChild);
      }
      console.log('hi_0');
      if (index>=1 && index<n_plots) {
        var divlabel2 = 'container' + index
        var div2 = document.getElementById(divlabel2); // CK: Not sure if this is necessary? To ensure the div is clear first
        div2.style.display = 'flex'
      }
      console.log('hi_1');
      vm.showGraphDivs[index] = true;
      console.log('hi_2');
      mpld3.draw_figure(divlabel, graphdata[index], function (fig, element) {
        console.log('hi_3');
        fig.setXTicks(6, function (d) {
          return d3.format('.0f')(d);
        });
        console.log('hi_4');
        fig.setYTicks(null, function (d) {
          return d3.format('.2s')(d);
        });
      });
    }
  status.succeed(vm, 'Graphs created') // CK: This should be a promise, otherwise this appears before the graphs do
  })
}

function clearGraphs(vm) {
  for (var index = 0; index <= 100; index++) {
    var divlabel = 'fig' + index
    var div = document.getElementById(divlabel); // CK: Not sure if this is necessary? To ensure the div is clear first
    while (div.firstChild) {
      div.removeChild(div.firstChild);
    }
    vm.hasGraphs = false
  }
}

function exportGraphs(vm) {
  return new Promise((resolve, reject) => {
    console.log('exportGraphs() called')
    rpcs.download('download_graphs', [])
    .then(response => {
      resolve(response)
    })
    .catch(error => {
      status.failurePopup(vm, 'Could not download graphs: ' + error.message)
      reject(error)
    })
  })
}

function exportResults(vm, serverDatastoreId) {
  return new Promise((resolve, reject) => {  
    console.log('exportResults() called TEMP FIX')
    rpcs.download('export_results', [serverDatastoreId])
    .then(response => {
      resolve(response)
    })    
    .catch(error => {
      status.failurePopup(vm, 'Could not export results: ' + error.message)
      reject(error)      
    })
  })
}


//
// Graphs DOM functions
//

function showBrowserWindowSize() {
  var w = window.innerWidth;
  var h = window.innerHeight;
  var ow = window.outerWidth; //including toolbars and status bar etc.
  var oh = window.outerHeight;
  console.log('Browser window size:')
  console.log('Inner width: ', w)
  console.log('Inner height: ', h)
  console.log('Outer width: ', ow)
  console.log('Outer height: ', oh)
  window.alert('Browser window size:\n'+
    'Inner width: ' + w + '\n' +
    'Inner height: ' + h + '\n' +
    'Outer width: ' + ow + '\n' +
    'Outer height: ' + oh + '\n')
}

function scaleElem(svg, frac) {
  // It might ultimately be better to redraw the graph, but this works
  var width  = svg.getAttribute("width")
  var height = svg.getAttribute("height")
  var viewBox = svg.getAttribute("viewBox")
  if (!viewBox) {
    svg.setAttribute("viewBox",  '0 0 ' + width + ' ' + height)
  }
  // if this causes the image to look weird, you may want to look at "preserveAspectRatio" attribute
  svg.setAttribute("width",  width*frac)
  svg.setAttribute("height", height*frac)
}

function scaleFigs(frac) {
  var graphs = window.top.document.querySelectorAll('svg.mpld3-figure')
  for (var g = 0; g < graphs.length; g++) {
    scaleElem(graphs[g], frac)
  }
}



//
// Legend functions
// 



function addListener(vm) {
  document.addEventListener('mousemove', function(e){onMouseUpdate(e, vm)}, false);
}



function onMouseUpdate(e, vm) {
  vm.mousex = e.pageX;
  vm.mousey = e.pageY;
  // console.log(vm.mousex, vm.mousey)
}

function createDialogs(vm) {
  var vals = placeholders(vm)
  for (var val in vals) {
    newDialog(vm, val, 'Dialog '+val, 'This is test '+val)
  }
}

// Create a new dialog
function newDialog(vm, id, name, content) {
  let options = {}
  let properties = { id, name, content, options }
  return vm.closedDialogs.push(properties)
}

function findDialog(vm, id, dialogs) {
  let index = dialogs.findIndex((val) => {
      return String(val.id) === String(id) // Force type conversion
    })
  return (index > -1) ? index : null
}

// "Show" the dialog
function maximize(vm,id) {
  let index = findDialog(vm, id, vm.closedDialogs)
  if (index !== null) {
    vm.closedDialogs[index].options.left = vm.mousex // Before opening, move it to where the mouse currently is
    vm.closedDialogs[index].options.top = vm.mousey
    vm.openDialogs.push(vm.closedDialogs[index])
    vm.closedDialogs.splice(index, 1)
  }
}

// "Hide" the dialog
function minimize(vm, id) {
  let index = findDialog(vm, id, vm.openDialogs)
  if (index !== null) {
    vm.closedDialogs.push(vm.openDialogs[index])
    vm.openDialogs.splice(index, 1)
  }
}


export default {
  sleep,
  getUniqueName,
  placeholders,
  projectID,
  hasData,
  hasPrograms,
  simStart,
  simEnd,
  simYears,
  activePops,
  getPlotOptions,
  makeGraphs,
  clearGraphs,
  exportGraphs,
  exportResults,
  scaleFigs,
  showBrowserWindowSize,
  
  addListener,
  onMouseUpdate,
  createDialogs,
  newDialog,
  findDialog,
  maximize,
  minimize
  
}