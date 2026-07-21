interface Props {
  size?: number
}

export default function CairnMark({ size = 28 }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 256 256"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="tawn"
    >
      <ellipse cx="128" cy="192" rx="62" ry="24" fill="var(--tawn-text)" />
      <ellipse cx="128" cy="148" rx="45" ry="21" fill="var(--tawn-text)" />
      <ellipse cx="128" cy="108" rx="27" ry="17" fill="var(--tawn-lapis)" />
    </svg>
  )
}
