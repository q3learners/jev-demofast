'use client'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
export default function LoginForm() {
  const router = useRouter()
  return (<form onSubmit={() => {}}>
    <label>Email</label><input type="email" placeholder="you@school.edu" />
    <input type="password" aria-label="Password" />
    <button type="submit">Sign in</button>
    <Link href="/auth/forgot-password">Forgot password?</Link>
    <button onClick={() => router.push('/signup')}>Create account</button>
  </form>)
}
