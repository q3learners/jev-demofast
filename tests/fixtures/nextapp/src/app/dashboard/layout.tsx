import Link from 'next/link'
const nav = [{ href: '/dashboard', label: 'Team' }, { href: '/dashboard/settings', label: 'Settings' }]
export default function DashboardLayout({ children }) {
  return (<div><aside>{nav.map(n => <Link key={n.href} href={n.href}>{n.label}</Link>)}</aside>{children}</div>)
}
