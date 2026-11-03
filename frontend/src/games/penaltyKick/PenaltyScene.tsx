import { useId, type PointerEventHandler, type Ref } from 'react'
import { BALL_R, GOAL, GOAL_H, GOAL_W, SPOT, VIEW, type Pt } from './geometry'

const SKY = '#0E1A33'
const STANDS = '#1B2A4A'
const CROWD = '#3B4C75'
const GRASS = ['#37A04F', '#2F8F46']
const NET_BACK = '#13233F'
const NET_LINE = '#C9D3E6'
const AIM = '#FFD500'
const SKIN = '#E0AC69'
const HAIR = '#2B1B12'
const DARK = '#1A1A1A'

export interface SceneProps {
  svgRef: Ref<SVGSVGElement>
  shooterColor: string
  keeperColor: string
  /** Offset of the keeper's hands from home and a lean, in SVG units and degrees. */
  keeper: { dx: number; dy: number; angle: number }
  ball: Pt & { r: number }
  /** The shooter's swipe in progress: the trail end, and whether the target ring shows. */
  trail: { to: Pt; ring: boolean } | null
  ripple: boolean
  kicking: boolean
  onPointerDown?: PointerEventHandler<SVGSVGElement>
  onPointerMove?: PointerEventHandler<SVGSVGElement>
  onPointerUp?: PointerEventHandler<SVGSVGElement>
  onPointerCancel?: PointerEventHandler<SVGSVGElement>
}

/** The night stadium: goal, keeper, ball on the spot and the kicker seen from behind. */
export function PenaltyScene({ svgRef, shooterColor, keeperColor, keeper, ball, trail, ripple, kicking, ...handlers }: SceneProps) {
  const uid = useId().replace(/:/g, '')
  const crowd = `pk-crowd-${uid}`
  const net = `pk-net-${uid}`
  const bands = Array.from({ length: Math.ceil((VIEW.height - 166) / 64) }, (_, i) => 166 + i * 64)
  return (
    <svg
      ref={svgRef}
      className="pk-scene__svg"
      viewBox={`0 0 ${VIEW.width} ${VIEW.height}`}
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      {...handlers}
    >
      <defs>
        <pattern id={crowd} width={12} height={10} patternUnits="userSpaceOnUse">
          <circle cx={3} cy={3} r={2.2} fill={CROWD} />
          <circle cx={9} cy={8} r={2.2} fill={CROWD} />
        </pattern>
        <pattern id={net} width={14} height={14} patternUnits="userSpaceOnUse">
          <path d="M0 0 L14 14 M14 0 L0 14" stroke={NET_LINE} strokeWidth={1} opacity={0.35} />
        </pattern>
      </defs>
      <rect width={VIEW.width} height={VIEW.height} fill={SKY} />
      <rect y={96} width={VIEW.width} height={70} fill={STANDS} />
      <rect y={96} width={VIEW.width} height={70} fill={`url(#${crowd})`} />
      {bands.map((y, i) => (
        <rect key={y} y={y} width={VIEW.width} height={64} fill={GRASS[i % 2]} />
      ))}
      <g stroke="#FFFFFF" strokeWidth={3} fill="none" opacity={0.9}>
        <line x1={0} y1={GOAL.bottom} x2={VIEW.width} y2={GOAL.bottom} />
        <path d={`M-10 ${GOAL.bottom} L-70 700 L460 700 L400 ${GOAL.bottom}`} />
        <path d={`M28 ${GOAL.bottom} L12 412 L378 412 L362 ${GOAL.bottom}`} />
      </g>
      <ellipse cx={SPOT.x} cy={SPOT.y + 2} rx={6} ry={3} fill="#FFFFFF" />

      <g className={ripple ? 'pk-net pk-net--ripple' : 'pk-net'}>
        <rect x={GOAL.left} y={GOAL.top} width={GOAL_W} height={GOAL_H} fill={NET_BACK} />
        <rect x={GOAL.left} y={GOAL.top} width={GOAL_W} height={GOAL_H} fill={`url(#${net})`} />
      </g>
      <path
        d={`M${GOAL.left} ${GOAL.bottom} V${GOAL.top} H${GOAL.right} V${GOAL.bottom}`}
        fill="none"
        stroke="#FFFFFF"
        strokeWidth={8}
        strokeLinejoin="round"
      />

      <g
        className="pk-keeper"
        data-testid="pk-keeper"
        style={{ transform: `translate(${keeper.dx}px, ${keeper.dy}px) rotate(${keeper.angle}deg)` }}
      >
        <Keeper color={keeperColor} />
      </g>

      <g className={kicking ? 'pk-kicker pk-kicker--kick' : 'pk-kicker'}>
        <Kicker color={shooterColor} />
      </g>

      {trail && (
        <g data-testid="pk-trail">
          <line
            x1={SPOT.x}
            y1={SPOT.y}
            x2={trail.to.x}
            y2={trail.to.y}
            stroke={AIM}
            strokeWidth={4}
            strokeDasharray="1 12"
            strokeLinecap="round"
          />
          {trail.ring && (
            <g stroke={AIM} strokeWidth={3} fill="none">
              <circle cx={trail.to.x} cy={trail.to.y} r={18} />
              <line x1={trail.to.x - 26} y1={trail.to.y} x2={trail.to.x + 26} y2={trail.to.y} />
              <line x1={trail.to.x} y1={trail.to.y - 26} x2={trail.to.x} y2={trail.to.y + 26} />
            </g>
          )}
        </g>
      )}

      <g data-testid="pk-ball" transform={`translate(${ball.x} ${ball.y}) scale(${ball.r / BALL_R})`}>
        <circle r={BALL_R} fill="#FFFFFF" stroke={DARK} strokeWidth={1.5} />
        <path d="M0 -6 L6 -2 L4 5 L-4 5 L-6 -2 Z" fill={DARK} />
        <path d="M-15 -6 L-10 -3 M10 -3 L15 -6 M-6 14 L-4 5 M6 14 L4 5 M0 -16 L0 -6" stroke={DARK} strokeWidth={1.5} />
      </g>
    </svg>
  )
}

/** Facing the viewer, hands at home (195, 276), feet on the goal line. */
function Keeper({ color }: { color: string }) {
  return (
    <>
      <rect x={183} y={300} width={9} height={28} fill={SKIN} />
      <rect x={198} y={300} width={9} height={28} fill={SKIN} />
      <rect x={181} y={324} width={12} height={6} rx={2} fill={DARK} />
      <rect x={197} y={324} width={12} height={6} rx={2} fill={DARK} />
      <rect x={180} y={284} width={30} height={20} rx={3} fill={DARK} />
      <path d="M181 240 L167 276 M209 240 L223 276" stroke={color} strokeWidth={8} strokeLinecap="round" />
      <rect x={179} y={232} width={32} height={56} rx={9} fill={color} />
      <circle cx={167} cy={276} r={7} fill="#FFFFFF" />
      <circle cx={223} cy={276} r={7} fill="#FFFFFF" />
      <circle cx={195} cy={218} r={13} fill={SKIN} />
      <path d="M182 216 A13 13 0 0 1 208 216 L208 212 A13 10 0 0 0 182 212 Z" fill={HAIR} />
    </>
  )
}

/** Seen from behind, to the left of the ball. */
function Kicker({ color }: { color: string }) {
  return (
    <>
      <rect x={127} y={652} width={13} height={50} rx={4} fill={SKIN} />
      <rect x={147} y={652} width={13} height={50} rx={4} fill={SKIN} />
      <rect x={125} y={694} width={17} height={12} rx={4} fill={DARK} />
      <rect x={145} y={694} width={17} height={12} rx={4} fill={DARK} />
      <rect x={122} y={624} width={42} height={36} rx={6} fill="#FFFFFF" />
      <path d="M118 560 L106 620 M168 560 L180 620" stroke={SKIN} strokeWidth={10} strokeLinecap="round" />
      <path d="M116 556 Q143 538 170 556 L166 632 L120 632 Z" fill={color} />
      <text x={143} y={606} textAnchor="middle" fontSize={30} fontWeight={800} fill="#FFFFFF">
        10
      </text>
      <rect x={137} y={536} width={12} height={12} fill={SKIN} />
      <circle cx={143} cy={524} r={18} fill={HAIR} />
    </>
  )
}
