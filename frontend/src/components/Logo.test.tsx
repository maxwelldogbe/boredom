import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Logo } from './Logo'

describe('Logo', () => {
  it('shows the lowercase wordmark next to a decorative mark', () => {
    const { container } = render(<Logo />)
    expect(screen.getByText('boredom')).toBeInTheDocument()
    expect(container.querySelector('img')).toHaveAttribute('alt', '')
    expect(container.querySelector('source')).toHaveAttribute('srcset', '/boredom-mark-inverse.svg')
  })

  it('names the mark-only variant for screen readers', () => {
    render(<Logo variant="mark" size={24} />)
    const img = screen.getByRole('img', { name: 'boredom' })
    expect(img).toHaveAttribute('width', '24')
    expect(img).toHaveAttribute('height', '24')
  })

  it('uses the inverse mark on dark backgrounds', () => {
    render(<Logo variant="mark" tone="dark" />)
    expect(screen.getByRole('img', { name: 'boredom' })).toHaveAttribute('src', '/boredom-mark-inverse.svg')
  })
})
