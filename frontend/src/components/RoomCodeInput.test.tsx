import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { RoomCodeInput } from './RoomCodeInput'

function Harness({ onComplete }: { onComplete?: (v: string) => void }) {
  const [value, setValue] = useState('')
  return (
    <>
      <RoomCodeInput value={value} onChange={setValue} onComplete={onComplete} />
      <output>{value}</output>
    </>
  )
}

const boxes = () => screen.getAllByRole('textbox') as HTMLInputElement[]

describe('RoomCodeInput', () => {
  it('renders 4 labelled boxes', () => {
    render(<Harness />)
    expect(boxes()).toHaveLength(4)
    expect(screen.getByLabelText('Room code letter 1')).toBeInTheDocument()
  })

  it('uppercases, ignores non-letters and auto-advances', () => {
    render(<Harness />)
    fireEvent.change(boxes()[0], { target: { value: 'a' } })
    expect(document.activeElement).toBe(boxes()[1])
    fireEvent.change(boxes()[1], { target: { value: '7' } })
    fireEvent.change(boxes()[1], { target: { value: 'b' } })
    expect(document.querySelector('output')?.textContent).toBe('AB')
  })

  it('fills every box from a paste and reports completion', () => {
    const onComplete = vi.fn()
    render(<Harness onComplete={onComplete} />)
    fireEvent.paste(boxes()[0], { clipboardData: { getData: () => ' wx-yz ' } })
    expect(boxes().map((b) => b.value)).toEqual(['W', 'X', 'Y', 'Z'])
    expect(onComplete).toHaveBeenCalledWith('WXYZ')
  })

  it('backspace on an empty box clears the previous one', () => {
    render(<Harness />)
    fireEvent.change(boxes()[0], { target: { value: 'a' } })
    fireEvent.change(boxes()[1], { target: { value: 'b' } })
    fireEvent.keyDown(boxes()[2], { key: 'Backspace' })
    expect(document.querySelector('output')?.textContent).toBe('A')
    expect(document.activeElement).toBe(boxes()[1])
  })
})
