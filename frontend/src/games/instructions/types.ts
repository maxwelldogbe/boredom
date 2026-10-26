import type { ComponentType } from 'react'
import type { SharedConstants } from '../../lib/constants'

export interface InstructionReference {
  left: string
  verb: string
  right: string
}

export interface GameInstructions {
  title: string
  tagline: string
  goal: string
  steps: string[]
  rules: string[]
  points?: string[]
  challenge?: string[]
  visual?: ComponentType
  sections?: { title: string; items: string[] }[]
  tips: string[]
  reference?: InstructionReference[]
}

export interface InstructionContext {
  settings: Record<string, unknown>
  constants: SharedConstants
  playerCount: number
}

export type InstructionEntry = GameInstructions | ((context: InstructionContext) => GameInstructions)
