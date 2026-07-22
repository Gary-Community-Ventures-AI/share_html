import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from './ui/combobox'

export type AutocompleteOption = {
  value: string
  label: string
  description?: string
}

export default function Autocomplete({
  value,
  onValueChange,
  onOptionSelect,
  options,
  placeholder,
  ariaLabel,
  emptyText = 'No matches found.',
  required = false,
  showAddAction = false,
  portalContainer,
}: {
  value: string
  onValueChange: (value: string) => void
  onOptionSelect?: (option: AutocompleteOption) => void
  options: AutocompleteOption[]
  placeholder: string
  ariaLabel: string
  emptyText?: string
  required?: boolean
  showAddAction?: boolean
  portalContainer?: HTMLElement | null
}) {
  const selected = options.find((option) => option.value === value) ?? null

  return (
    <Combobox
      items={options}
      value={selected}
      inputValue={value}
      onInputValueChange={onValueChange}
      onValueChange={(option) => {
        if (!option) return
        onValueChange(option.value)
        onOptionSelect?.(option)
      }}
      itemToStringLabel={(option) => option.value}
      itemToStringValue={(option) => option.value}
      filter={(option, query) => `${option.label} ${option.value} ${option.description ?? ''}`.toLowerCase().includes(query.toLowerCase())}
      autoHighlight
      modal={false}
    >
      <ComboboxInput placeholder={placeholder} aria-label={ariaLabel} required={required} />
      <ComboboxContent container={portalContainer}>
        <ComboboxEmpty>{emptyText}</ComboboxEmpty>
        <ComboboxList>
          {(option: AutocompleteOption) => (
            <ComboboxItem key={option.value} value={option} action={showAddAction ? <span className="ui-combobox-item-action">+ Add</span> : undefined}>
              <strong>{option.label}</strong>
              {option.description && <small>{option.description}</small>}
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}
