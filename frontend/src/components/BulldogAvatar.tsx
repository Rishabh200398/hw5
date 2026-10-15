// Handsome Dan, the Campus Customs mascot (same as the shop website).
export default function BulldogAvatar({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="Handsome Dan the bulldog">
      <path d="M12 20 Q8 10 18 12 L22 22 Z" fill="#8c6a4a" />
      <path d="M52 20 Q56 10 46 12 L42 22 Z" fill="#8c6a4a" />
      <rect x="12" y="14" width="40" height="38" rx="18" fill="#f3ead9" />
      <path d="M12 26 Q32 6 52 26 L52 30 Q32 18 12 30 Z" fill="#00366b" />
      <circle cx="24" cy="30" r="4.2" fill="#2b2b2b" />
      <circle cx="40" cy="30" r="4.2" fill="#2b2b2b" />
      <circle cx="25.3" cy="28.8" r="1.3" fill="#fff" />
      <circle cx="41.3" cy="28.8" r="1.3" fill="#fff" />
      <ellipse cx="32" cy="42" rx="15" ry="11" fill="#fff" />
      <ellipse cx="32" cy="37" rx="6" ry="4.4" fill="#2b2b2b" />
      <path d="M32 41 L32 46 M32 46 Q27 48 25 45 M32 46 Q37 48 39 45" stroke="#6b6b6b" strokeWidth="1.6" fill="none" strokeLinecap="round" />
    </svg>
  )
}
