const items = [{ label: 'Catalog', href: '/courses' }, { label: 'About us', href: '/about' }]
export function Nav() { return <nav>{items.map(i => <a key={i.href} href={i.href}>{i.label}</a>)}</nav> }
