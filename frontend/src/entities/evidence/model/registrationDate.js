import {localDate} from '../../../shared/lib/format.js'

export function registrationDate(manual, suggested, today=localDate()) {
  return manual || suggested || today
}
