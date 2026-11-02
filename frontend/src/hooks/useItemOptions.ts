import { useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { getItems } from '../api/client'
import type { TypeaheadOption } from '../components/Typeahead'

/** How many items an item picker shows at once. The backend matches on code or
 *  name, so narrowing by typing is the way to reach anything past this. */
const PAGE = 200

/**
 * Server-side item search for a Typeahead.
 *
 * Replaces the old pattern of fetching every item (`getItems()` with its 10,000
 * row ceiling) and filtering in the browser: with ~13k items the overflow was
 * never fetched, so those items could not be selected and typing their code
 * found nothing. Matching now happens in SQL, so any item is reachable.
 *
 *   const items = useItemOptions()
 *   <Typeahead options={items.options} onQueryChange={items.onQueryChange}
 *              loading={items.loading} value={…} onChange={…} />
 */
export function useItemOptions() {
  const [query, setQuery] = useState('')
  const term = query.trim()

  const { data = [], isFetching } = useQuery({
    queryKey: ['items', 'search', term],
    queryFn: () => getItems(term ? { search: term, limit: PAGE } : { limit: PAGE }),
    // Keep the previous matches on screen while the next request is in flight,
    // so the dropdown does not flash empty on every keystroke.
    placeholderData: keepPreviousData,
  })

  const options: TypeaheadOption[] = useMemo(
    () => (data as any[]).map(i => ({ value: String(i.id), label: `${i.code} — ${i.name}` })),
    [data],
  )

  return { options, onQueryChange: setQuery, loading: isFetching, items: data as any[] }
}
