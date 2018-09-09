/*
 * Heftier functions that are shared across pages
 */

import utils from '@/js/utils'
import rpcs from '@/js/rpc-service'
import status from '@/js/status-service'

function validateYears(vm) {
  if      (vm.startYear > vm.simEnd)   { vm.startYear = vm.simEnd }
  else if (vm.startYear < vm.simStart) { vm.startYear = vm.simStart }
  if      (vm.endYear   > vm.simEnd)   { vm.endYear   = vm.simEnd }
  else if (vm.endYear   < vm.simStart) { vm.endYear   = vm.simStart }
}

function updateSets(vm) {
  return new Promise((resolve, reject) => {
    console.log('updateSets() called')
    rpcs.rpc('get_parset_info', [vm.projectID]) // Get the current user's parsets from the server.
      .then(response => {
        vm.parsetOptions = response.data // Set the scenarios to what we received.
        if (vm.parsetOptions.indexOf(vm.activeParset) === -1) {
          console.log('Parameter set ' + vm.activeParset + ' no longer found')
          vm.activeParset = vm.parsetOptions[0] // If the active parset no longer exists in the array, reset it
        } else {
          console.log('Parameter set ' + vm.activeParset + ' still found')
        }
        vm.newParsetName = vm.activeParset // WARNING, KLUDGY
        console.log('Parset options: ' + vm.parsetOptions)
        console.log('Active parset: ' + vm.activeParset)
        rpcs.rpc('get_progset_info', [vm.projectID]) // Get the current user's progsets from the server.
          .then(response => {
            vm.progsetOptions = response.data // Set the scenarios to what we received.
            if (vm.progsetOptions.indexOf(vm.activeProgset) === -1) {
              console.log('Program set ' + vm.activeProgset + ' no longer found')
              vm.activeProgset = vm.progsetOptions[0] // If the active parset no longer exists in the array, reset it
            } else {
              console.log('Program set ' + vm.activeProgset + ' still found')
            }
            vm.newProgsetName = vm.activeProgset // WARNING, KLUDGY
            console.log('Progset options: ' + vm.progsetOptions)
            console.log('Active progset: ' + vm.activeProgset)
            resolve(response)
          })
          .catch(error => {
            status.fail(this, 'Could not get progset info', error)
            reject(error)
          })
      })
      .catch(error => {
        status.fail(this, 'Could not get parset info', error)
        reject(error)
      })
  })
    .catch(error => {
      status.fail(this, 'Could not get parset info', error)
      reject(error)
    })
}

function exportGraphs(vm, serverDatastoreId) {
  return new Promise((resolve, reject) => {
    console.log('exportGraphs() called')
    rpcs.download('download_graphs', [serverDatastoreId])
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





export default {
  validateYears,
  updateSets,
  exportGraphs,
  exportResults,
}