export function Whale({ mini = false, className = '' }: { mini?: boolean; className?: string }) {
  if (mini) return <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden="true"><rect width="40" height="40" rx="13" fill="#4D7FF0"/><path d="M8 23c0-6 4-10 10-10 5 0 8 3 9 7 3 0 5-2 5-5 3 6 0 12-7 13-10 3-17 1-17-5Z" fill="white"/><path d="M13 25c5 3 10 3 15-1-1 5-9 8-14 4Z" fill="#DCE9FF"/><circle cx="16" cy="21" r="1.4" fill="#3C5C9F"/><path d="M19 10c-2-4-5-3-4 0m4 0c0-5 4-5 4-1" stroke="white" strokeWidth="1.7" strokeLinecap="round"/></svg>
  return <svg className={'whale-illustration ' + className} viewBox="0 0 360 230" fill="none" role="img" aria-label="一只正在好奇地冲浪的蓝色小鲸鱼">
    <ellipse cx="182" cy="198" rx="99" ry="11" fill="#E8EEF9"/>
    <path d="M65 115c-1-36 28-60 70-60 35 0 66 19 79 50 25 7 49-4 63-32 11 31-1 58-31 73-20 39-83 55-130 38-34-12-51-35-51-69Z" fill="#729DF3"/>
    <path d="M69 140c24 28 89 34 147-1 8-5 17-6 30 7-20 39-83 55-130 38-24-8-40-23-47-44Z" fill="#D9E6FF"/>
    <path d="M166 150c16 0 24 10 22 26-16 1-30-8-30-17 0-5 3-8 8-9Z" fill="#5886DB"/>
    <path d="M278 79c-2-16 7-27 22-28-2 16-10 26-22 28Z" fill="#8EAEF0"/>
    <circle cx="112" cy="120" r="5" fill="#2F4E82"/><circle cx="113.5" cy="118.5" r="1.5" fill="white"/>
    <path d="M122 135c5 5 10 5 15 0" stroke="#3D6299" strokeWidth="3" strokeLinecap="round"/>
    <ellipse cx="97" cy="135" rx="10" ry="5" fill="#F3C4B7" fillOpacity=".8"/>
    <path d="M144 40c-4-16-15-21-22-13m22 13c3-21 16-27 24-18" stroke="#90B5F5" strokeWidth="6" strokeLinecap="round"/>
    <circle cx="119" cy="20" r="4" fill="#BDD3F8"/><circle cx="174" cy="15" r="3" fill="#BDD3F8"/>
    <path d="m285 151 3 7 8 2-7 3-2 8-3-8-7-2 8-3Z" fill="#E6BB6D"/>
    <path d="m45 69 2 5 6 2-5 2-2 6-2-5-5-2 5-2Z" fill="#B6C5E5"/>
    <circle cx="295" cy="122" r="4" stroke="#D8E3F7" strokeWidth="2"/>
    <path d="M42 180c10-6 20-6 30 0m175 7c11-5 23-5 34 0" stroke="#CCDDF6" strokeWidth="2" strokeLinecap="round"/>
  </svg>
}
