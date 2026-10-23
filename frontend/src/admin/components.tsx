import { useId, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { ActorRef, DayCount, Paged, RangeOption } from './api'
import { actorPath, fmtDay, fmtInt, niceMax } from './format'

export function StatTile({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat__label">{label}</div>
      <div className="stat__value">{value}</div>
      {hint && <div className="stat__hint">{hint}</div>}
    </div>
  )
}

/** Date-range presets in one row above everything they scope. */
export function RangeFilter({
  ranges,
  value,
  onChange,
}: {
  ranges: RangeOption[]
  value: string
  onChange: (key: string) => void
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label="Date range">
      {ranges.map((r) => (
        <button
          key={r.key}
          type="button"
          role="radio"
          aria-checked={r.key === value}
          className="segmented__option"
          onClick={() => onChange(r.key)}
        >
          {r.label}
        </button>
      ))}
    </div>
  )
}

export function Pager({ page, onPage }: { page: Paged; onPage: (n: number) => void }) {
  if (page.numPages <= 1) return <p className="muted admin-count">{fmtInt(page.count)} total</p>
  return (
    <nav className="pager" aria-label="Pages">
      <button type="button" className="btn btn--ghost" disabled={page.page <= 1} onClick={() => onPage(page.page - 1)}>
        ‹ Previous
      </button>
      <span className="muted">
        Page {page.page} of {page.numPages} ({fmtInt(page.count)} total)
      </span>
      <button
        type="button"
        className="btn btn--ghost"
        disabled={page.page >= page.numPages}
        onClick={() => onPage(page.page + 1)}
      >
        Next ›
      </button>
    </nav>
  )
}

export function TypeBadge({ actor }: { actor: Pick<ActorRef, 'kind' | 'shortKey' | 'guestKey'> }) {
  return actor.kind === 'registered' ? (
    <span className="badge badge--registered">registered</span>
  ) : (
    <span className="badge" title="Approximate (browser-based)">
      guest {actor.shortKey ?? actor.guestKey?.slice(0, 8)}
    </span>
  )
}

/** A player's name linking to their detail page, with a type badge. */
export function ActorLink({ actor }: { actor: ActorRef }) {
  return (
    <span className="actor">
      <Link to={actorPath(actor)}>{actor.name}</Link> <TypeBadge actor={actor} />
    </span>
  )
}

/** A magnitude bar inside a table cell (value text stays beside it, in ink). */
export function InlineBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 && value > 0 ? Math.max(2, (value / max) * 100) : 0
  return (
    <span className="inline-bar" aria-hidden="true">
      <span className="inline-bar__fill" style={{ width: `${pct}%` }} />
    </span>
  )
}

export function LoadState({ error, loading }: { error: Error | null; loading: boolean }) {
  if (error)
    return (
      <p className="field__error" role="alert">
        {error.message}
      </p>
    )
  return loading ? <p className="muted">Loading…</p> : null
}

/** Refetch keeps the frame: the previous render stays, dimmed, until new data arrives. */
export function Refreshing({ active, children }: { active: boolean; children: ReactNode }) {
  return (
    <div className={active ? 'refreshing' : undefined} aria-busy={active || undefined}>
      {children}
    </div>
  )
}

/**
 * Columns, one per day (single series, so no legend: the heading names it). Each column is
 * focusable and shows its value on hover or focus; a table view carries every value too.
 */
export function DailyColumns({ series, label, unit = 'games' }: { series: DayCount[]; label: string; unit?: string }) {
  const [active, setActive] = useState<number | null>(null)
  const tableId = useId()
  const peak = Math.max(0, ...series.map((d) => d.count))
  const top = niceMax(peak)
  const ticks = top >= 2 ? [top, top / 2, 0] : [top, 0]
  const total = series.reduce((sum, d) => sum + d.count, 0)
  const current = active === null ? null : series[active]

  return (
    <figure className="chart">
      <div className="chart__frame">
        <div className="chart__axis" aria-hidden="true">
          {ticks.map((t) => (
            <span key={t} style={{ bottom: `${(t / top) * 100}%` }}>
              {fmtInt(t)}
            </span>
          ))}
        </div>
        <div className="chart__plot" role="group" aria-label={`${label}: ${fmtInt(total)} ${unit} in total`}>
          {ticks.map((t) => (
            <span key={t} className="chart__grid" style={{ bottom: `${(t / top) * 100}%` }} aria-hidden="true" />
          ))}
          {series.map((d, i) => (
            <span
              key={d.date}
              className={`chart__slot${active === i ? ' chart__slot--active' : ''}`}
              tabIndex={0}
              aria-label={`${fmtDay(d.date)}: ${d.count} ${unit}`}
              onPointerEnter={() => setActive(i)}
              onPointerLeave={() => setActive((a) => (a === i ? null : a))}
              onFocus={() => setActive(i)}
              onBlur={() => setActive((a) => (a === i ? null : a))}
            >
              <span className="chart__bar" style={{ height: `${(d.count / top) * 100}%` }} />
            </span>
          ))}
          {current && active !== null && (
            <span
              className="chart__tip"
              role="status"
              style={{ left: `${((active + 0.5) / series.length) * 100}%` }}
            >
              <strong>{fmtInt(current.count)}</strong> <span className="muted">{fmtDay(current.date)}</span>
            </span>
          )}
        </div>
      </div>
      {series.length > 0 && (
        <div className="chart__x" aria-hidden="true">
          <span>{fmtDay(series[0].date, false)}</span>
          <span>{fmtDay(series[series.length - 1].date, false)}</span>
        </div>
      )}
      <details className="chart__table">
        <summary aria-controls={tableId}>Show as table</summary>
        <table id={tableId} className="admin-table">
          <thead>
            <tr>
              <th scope="col">Day</th>
              <th scope="col" className="num">
                {unit[0].toUpperCase() + unit.slice(1)}
              </th>
            </tr>
          </thead>
          <tbody>
            {series.map((d) => (
              <tr key={d.date}>
                <td>{fmtDay(d.date)}</td>
                <td className="num">{d.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  )
}
