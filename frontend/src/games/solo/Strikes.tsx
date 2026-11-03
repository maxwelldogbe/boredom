/** Strikes as icons and as text ("Strikes 1 of 3"), for the solo challenges. */
export function Strikes({ strikes, max }: { strikes: number; max: number }) {
  return (
    <p className="solo-run__strikes">
      <span aria-hidden="true">
        {Array.from({ length: max }, (_, i) => (
          <span key={i} className={i < strikes ? 'solo-run__strike solo-run__strike--on' : 'solo-run__strike'}>
            ✕
          </span>
        ))}
      </span>
      <span>
        Strikes {strikes} of {max}
      </span>
    </p>
  )
}
