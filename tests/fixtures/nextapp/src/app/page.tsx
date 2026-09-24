import Link from 'next/link'
import { Nav } from '@/components/Nav'
export default function Home() {
  return (<main><Nav /><h1>Learn anything with a voice tutor</h1><Link href="/login">Log in</Link></main>)
}
