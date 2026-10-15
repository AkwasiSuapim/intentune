import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { size?: number }

function Icon({ size = 24, children, ...rest }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...rest}
    >
      {children}
    </svg>
  )
}

function SolidIcon(props: IconProps) {
  return <Icon fill="currentColor" stroke="none" {...props} />
}

export function WaveformIcon(props: IconProps) {
  return (
    <Icon strokeWidth="1.8" {...props}>
      <path d="M3 12c1.5 0 1.5-3 3-3s1.5 6 3 6 1.5-9 3-9 1.5 9 3 9 1.5-6 3-6 1.5 3 3 3" />
    </Icon>
  )
}

export function MenuIcon(props: IconProps) {
  return (
    <Icon strokeWidth="1.8" {...props}>
      <path d="M4 7h16M4 12h11M4 17h16" />
    </Icon>
  )
}

export function PlusIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 5v14M5 12h14" />
    </Icon>
  )
}

export function CloseIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Icon>
  )
}

export function CheckIcon(props: IconProps) {
  return (
    <Icon strokeWidth="2.4" {...props}>
      <path d="M5 12.5l4.5 4.5L19 7" />
    </Icon>
  )
}

export function ChevronRightIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M9 6l6 6-6 6" />
    </Icon>
  )
}

export function ArrowRightIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </Icon>
  )
}

export function ArrowUpIcon(props: IconProps) {
  return (
    <Icon strokeWidth="2.2" {...props}>
      <path d="M12 19V5M6 11l6-6 6 6" />
    </Icon>
  )
}

export function RestoreIcon(props: IconProps) {
  return (
    <Icon strokeWidth="1.8" {...props}>
      <path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4" />
    </Icon>
  )
}

export function TuneIcon(props: IconProps) {
  return (
    <Icon strokeWidth="1.9" {...props}>
      <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
      <circle cx="15" cy="7" r="2" />
      <circle cx="9" cy="17" r="2" />
    </Icon>
  )
}

export function HeartIcon({
  filled = false,
  ...props
}: IconProps & { filled?: boolean }) {
  return (
    <Icon
      strokeWidth="1.8"
      fill={filled ? 'currentColor' : 'none'}
      {...props}
    >
      <path d="M12 20s-7-4.35-7-10a4 4 0 0 1 7-2.65A4 4 0 0 1 19 10c0 5.65-7 10-7 10z" />
    </Icon>
  )
}

export function PlayIcon(props: IconProps) {
  return (
    <SolidIcon {...props}>
      <path d="M8 5.5v13l11-6.5z" />
    </SolidIcon>
  )
}

export function PauseIcon(props: IconProps) {
  return (
    <SolidIcon {...props}>
      <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" />
    </SolidIcon>
  )
}

export function NextIcon(props: IconProps) {
  return (
    <SolidIcon {...props}>
      <path d="M6 6l9 6-9 6z" />
      <path
        d="M17.5 6v12"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </SolidIcon>
  )
}
