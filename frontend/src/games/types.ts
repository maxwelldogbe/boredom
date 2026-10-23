import type { ComponentType } from 'react'
import type { RoomPublic } from '../types/protocol'
import type { GameViewPush } from '../types/views'

export type GameAction = { type: string } & Record<string, unknown>

/** Props every game UI receives. `send` resolves false if the server rejected the action. */
export interface GameUiProps<V> {
  view: V
  send: (action: GameAction) => Promise<boolean>
  me: string
  room: RoomPublic
}

export interface SettingOption {
  value: string | number | boolean
  label: string
}

export interface SettingDef {
  key: string
  label: string
  options: SettingOption[]
}

export type ImplementedGameId = GameViewPush['gameId']
export type ViewOf<G extends ImplementedGameId> = Extract<GameViewPush, { gameId: G }>['view']

/** Picker metadata + UI for one game. Values come from core/PROTOCOL.md section 7. */
export interface GameUi<G extends ImplementedGameId> {
  id: G
  name: string
  icon: string
  description: string
  minPlayers: number
  maxPlayers: number
  settings: SettingDef[]
  Component: ComponentType<GameUiProps<ViewOf<G>>>
}
