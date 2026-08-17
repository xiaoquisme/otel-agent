/** Open a request detail route in a named browser window. */
export function openRequestWindow(id: number): void {
  const url = `/request/${id}`
  const target = `otel-request-${id}`
  const opened = window.open(url, target)
  if (opened === null) {
    window.location.assign(url)
    return
  }
  opened.focus()
}
