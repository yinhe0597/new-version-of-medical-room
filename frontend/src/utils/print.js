export const RECEIPT_PRINT_STYLES = `
body {
  font-family: 'Courier New', Courier, monospace;
  padding: 10px;
  line-height: 1.6;
  margin: 0;
}
p { margin: 4px 0; }
h3 { text-align: center; }
hr { border: none; border-top: 1px dashed #999; margin: 8px 0; }
.receipt-preview { padding: 10px; }
.item-line { margin: 2px 0 2px 10px; font-size: 12px; line-height: 1.4; }
.advice-print-info { font-size: 12px; }
`

export function printElement(element, {
  title = '打印',
  styles = '',
  copyDocumentStyles = false,
  header = '',
  subheader = '',
} = {}) {
  if (!element) return false

  const printWindow = window.open('', '_blank', 'width=400,height=600')
  if (!printWindow) return false

  const printDocument = printWindow.document
  printDocument.title = title

  const meta = printDocument.createElement('meta')
  meta.setAttribute('charset', 'utf-8')
  printDocument.head.appendChild(meta)

  if (copyDocumentStyles) {
    document.querySelectorAll('link[rel="stylesheet"], style').forEach((node) => {
      printDocument.head.appendChild(node.cloneNode(true))
    })
  }

  if (styles) {
    const style = printDocument.createElement('style')
    style.textContent = styles
    printDocument.head.appendChild(style)
  }

  if (header) {
    const headerElement = printDocument.createElement('div')
    headerElement.className = 'print-header'
    headerElement.textContent = header
    printDocument.body.appendChild(headerElement)
  }

  if (subheader) {
    const subheaderElement = printDocument.createElement('div')
    subheaderElement.className = 'print-sub'
    subheaderElement.textContent = subheader
    printDocument.body.appendChild(subheaderElement)
  }

  const clone = element.cloneNode(true)
  clone.removeAttribute('id')
  clone.querySelectorAll('[id]').forEach((node) => node.removeAttribute('id'))
  printDocument.body.appendChild(clone)

  let printed = false
  const triggerPrint = () => {
    if (printed) return
    printed = true
    printWindow.focus()
    printWindow.print()
  }

  printWindow.onafterprint = () => printWindow.close()

  if (copyDocumentStyles) {
    if (printDocument.readyState === 'complete') {
      printWindow.setTimeout(triggerPrint, 100)
    } else {
      printWindow.addEventListener('load', () => printWindow.setTimeout(triggerPrint, 100))
      printWindow.setTimeout(triggerPrint, 1500)
    }
  } else {
    printWindow.setTimeout(triggerPrint, 0)
  }
  return true
}
