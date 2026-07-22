import * as React from 'react'
import { Combobox as ComboboxPrimitive } from '@base-ui/react'

const Combobox = ComboboxPrimitive.Root

function ComboboxInput({ className = '', ...props }: ComboboxPrimitive.Input.Props) {
  return <ComboboxPrimitive.Input data-slot="combobox-input" className={`ui-combobox-input ${className}`} {...props} />
}

function ComboboxContent({ className = '', sideOffset = 5, container, ...props }: ComboboxPrimitive.Popup.Props & Pick<ComboboxPrimitive.Positioner.Props, 'sideOffset'> & { container?: HTMLElement | null }) {
  return (
    <ComboboxPrimitive.Portal container={container}>
      <ComboboxPrimitive.Positioner sideOffset={sideOffset} className="ui-combobox-positioner">
        <ComboboxPrimitive.Popup data-slot="combobox-content" className={`ui-combobox-content ${className}`} {...props} />
      </ComboboxPrimitive.Positioner>
    </ComboboxPrimitive.Portal>
  )
}

function ComboboxList({ className = '', ...props }: ComboboxPrimitive.List.Props) {
  return <ComboboxPrimitive.List data-slot="combobox-list" className={`ui-combobox-list ${className}`} {...props} />
}

function ComboboxItem({ className = '', children, action, ...props }: ComboboxPrimitive.Item.Props & { action?: React.ReactNode }) {
  return (
    <ComboboxPrimitive.Item data-slot="combobox-item" className={`ui-combobox-item ${className}`} {...props}>
      <span className="ui-combobox-item-copy">{children}</span>
      {action}
      <ComboboxPrimitive.ItemIndicator className="ui-combobox-indicator">✓</ComboboxPrimitive.ItemIndicator>
    </ComboboxPrimitive.Item>
  )
}

function ComboboxEmpty({ className = '', ...props }: ComboboxPrimitive.Empty.Props) {
  return <ComboboxPrimitive.Empty data-slot="combobox-empty" className={`ui-combobox-empty ${className}`} {...props} />
}

export { Combobox, ComboboxContent, ComboboxEmpty, ComboboxInput, ComboboxItem, ComboboxList }
