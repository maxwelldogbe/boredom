import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '../../components/Button'
import { GameIcon } from '../../components/GameIcon'
import { HowToPlayModal } from '../../components/HowToPlayModal'
import { Modal } from '../../components/Modal'
import { gameInstructions } from '../../games/instructions'
import { GAME_UIS } from '../../games/registry'
import { CHALLENGE_INSTRUCTIONS, isChallenge } from '../../games/solo/instructions'
import { DOTS_GAME, SOLO_BOT_GAMES, SOLO_CHALLENGES, SOLO_TILE_RECORD_GAMES, soloSettings } from '../../games/soloGames'
import { getAuthToken } from '../../lib/account'
import { C } from '../../lib/constants'
import { friendlyError } from '../../lib/errors'
import { getProfile } from '../../lib/profileStore'
import {
  bestOf,
  difficultyLabel,
  DOTS_SIZES,
  fetchSoloRecords,
  GUESS_CONTENTS,
  markSoloHowToSeen,
  RANDOM_TOPIC,
  recordVariant,
  saveDifficulty,
  savedDifficulty,
  savedDotsSize,
  saveDotsSize,
  savedGuessContent,
  savedTopic,
  saveGuessContent,
  saveTopic,
  SOLO_DIFFICULTIES,
  soloHowToSeen,
  withBotLine,
  type GuessContent,
} from '../../lib/solo'
import { useRoomActions } from '../../state/context'
import type { GameId, SoloDifficulty, SoloRecordRow, SoloVariant } from '../../types/protocol'
import '../../games/solo/solo.css'

const SOLO_IDS: readonly GameId[] = [...SOLO_BOT_GAMES, ...SOLO_CHALLENGES.map((c) => c.id)]
const isSoloGame = (id: string | null): id is GameId => SOLO_IDS.some((g) => g === id)

/** /solo: pick a game to play alone, against a bot or for a personal best (registered players). */
export default function SoloPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { startSolo } = useRoomActions()
  const asked = params.get('game')
  const [open, setOpen] = useState<GameId | null>(() => (isSoloGame(asked) ? asked : null))
  // The first time a game's sheet opens, its instructions open on top of it.
  const [howTo, setHowTo] = useState(() => isSoloGame(asked) && !soloHowToSeen(asked))
  const [difficulty, setDifficulty] = useState<SoloDifficulty>(savedDifficulty)
  const [size, setSize] = useState(savedDotsSize)
  const [content, setContent] = useState<GuessContent>(savedGuessContent)
  const [topic, setTopic] = useState(savedTopic)
  const [records, setRecords] = useState<SoloRecordRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const token = getAuthToken()
    if (!token) return
    let live = true
    fetchSoloRecords(token)
      .then((rows) => live && setRecords(rows))
      .catch(() => {}) // the tiles just show no record
    return () => {
      live = false
    }
  }, [])

  if (getProfile()?.type !== 'registered') return <Navigate to="/" replace />

  const choice = { difficulty, size, content, topic }

  const openSheet = (gameId: GameId) => {
    setOpen(gameId)
    setError(null)
    setHowTo(!soloHowToSeen(gameId))
  }

  const recordLine = (gameId: GameId) => {
    const variant = recordVariant(gameId, choice)
    const row = records.find((r) => r.gameId === gameId && r.variant === variant)
    return row ? `Played ${row.plays}, won ${row.wins}` : 'No games yet'
  }

  const bestLine = (best: number | null) => (best === null ? 'No score yet' : `Best: ${best}`)

  const start = async () => {
    if (!open) return
    setBusy(true)
    setError(null)
    let variant: SoloVariant = { difficulty }
    if (open === DOTS_GAME) variant = { difficulty, size }
    else if (open === 'guess_race') variant = { content }
    else if (open === 'name_it') variant = { topic }
    else if (open === 'hangman') variant = {}
    try {
      const code = await startSolo(open, variant)
      navigate(`/room/${code}`)
    } catch (err) {
      setError(friendlyError(err))
      setBusy(false)
    }
  }

  const challenge = open ? SOLO_CHALLENGES.find((c) => c.id === open) : undefined
  const title = challenge ? challenge.title : open ? GAME_UIS[open as keyof typeof GAME_UIS].name : ''
  const instructions = !open
    ? null
    : isChallenge(open)
      ? CHALLENGE_INSTRUCTIONS[open]!()
      : (() => {
          const base = gameInstructions(open, { settings: soloSettings(open, size), constants: C, playerCount: 2 })
          return base ? withBotLine(base, difficulty, open) : null
        })()
  const sheetVariant = open ? recordVariant(open, choice) : null

  const chip = (on: boolean, label: string, onClick: () => void, key: string) => (
    <button key={key} type="button" role="radio" aria-checked={on} className={`solo__chip${on ? ' solo__chip--on' : ''}`} onClick={onClick}>
      {label}
    </button>
  )

  return (
    <main className="page stack solo">
      <Link to="/" className="back-link">
        ← Home
      </Link>
      <h1>Play alone</h1>
      <div className="game-cards solo__games">
        {SOLO_BOT_GAMES.map((id) => {
          const ui = GAME_UIS[id as keyof typeof GAME_UIS]
          return (
            <button key={id} type="button" className="game-card" onClick={() => openSheet(id)}>
              <span className="game-card__icon" aria-hidden="true">
                <GameIcon id={id} />
              </span>
              <span className="game-card__text">
                <strong>{ui.name}</strong>
                <span className="game-card__players">vs Bot</span>
                {SOLO_TILE_RECORD_GAMES.includes(id) && <span className="game-card__desc">{recordLine(id)}</span>}
              </span>
            </button>
          )
        })}
        {SOLO_CHALLENGES.map((c) => (
          <button key={c.id} type="button" className="game-card" onClick={() => openSheet(c.id)}>
            <span className="game-card__icon" aria-hidden="true">
              <GameIcon id={c.id} />
            </span>
            <span className="game-card__text">
              <strong>{c.title}</strong>
              <span className="game-card__desc">{bestLine(bestOf(records, c.id))}</span>
            </span>
          </button>
        ))}
      </div>

      {open && !howTo && (
        <Modal
          title={title}
          className="modal--sheet"
          onClose={() => !busy && setOpen(null)}
          actions={
            <>
              <Button block onClick={start} disabled={busy}>
                {busy ? 'Starting…' : 'Start'}
              </Button>
              <Button variant="ghost" block onClick={() => setHowTo(true)} disabled={busy}>
                How to play
              </Button>
            </>
          }
        >
          {!isChallenge(open) && (
            <div className="solo__chips" role="radiogroup" aria-label="Difficulty">
              {SOLO_DIFFICULTIES.map((d) =>
                chip(difficulty === d, difficultyLabel(d), () => {
                  setDifficulty(d)
                  saveDifficulty(d)
                }, d),
              )}
            </div>
          )}
          {open === DOTS_GAME && (
            <div className="solo__chips" role="radiogroup" aria-label="Board size">
              {DOTS_SIZES.map((n) =>
                chip(size === n, `${n}x${n}`, () => {
                  setSize(n)
                  saveDotsSize(n)
                }, String(n)),
              )}
            </div>
          )}
          {open === 'guess_race' && (
            <div className="solo__chips" role="radiogroup" aria-label="Puzzles">
              {GUESS_CONTENTS.map((c) =>
                chip(content === c.value, c.label, () => {
                  setContent(c.value)
                  saveGuessContent(c.value)
                }, c.value),
              )}
            </div>
          )}
          {open === 'name_it' && (
            <div className="solo__topics" role="radiogroup" aria-label="Topic">
              {[...C.SOLO_NAMEIT_TOPICS, { id: RANDOM_TOPIC, name: 'Surprise me' }].map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="radio"
                  aria-checked={topic === t.id}
                  className={`solo__topic${topic === t.id ? ' solo__topic--on' : ''}`}
                  onClick={() => {
                    setTopic(t.id)
                    saveTopic(t.id)
                  }}
                >
                  {t.name}
                </button>
              ))}
            </div>
          )}
          {isChallenge(open) && (
            <p className="muted">
              {sheetVariant === null ? bestLine(bestOf(records, open)) : bestLine(bestOf(records, open, sheetVariant))}
            </p>
          )}
          {error && (
            <p className="field__error" role="alert">
              {error}
            </p>
          )}
        </Modal>
      )}
      {open && howTo && instructions && (
        <HowToPlayModal
          content={instructions}
          roundsToWin={1}
          onClose={() => {
            markSoloHowToSeen(open)
            setHowTo(false)
          }}
        />
      )}
    </main>
  )
}
