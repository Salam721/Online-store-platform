import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { useCart } from '@/contexts/CartContext'

export default function NavBar() {
  const { isAuthenticated, logout } = useAuth()
  const { items } = useCart()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)

  const cartCount = items.reduce((sum, i) => sum + i.quantity, 0)

  function handleLogout() {
    logout()
    navigate('/')
  }

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `text-sm font-medium transition hover:text-blue-600 ${isActive ? 'text-blue-600' : 'text-gray-700'}`

  return (
    <nav className="sticky top-0 z-40 border-b border-gray-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link to="/" className="text-lg font-bold text-gray-900">
          ShopAPI
        </Link>

        {/* Desktop nav */}
        <div className="hidden items-center gap-6 sm:flex">
          <NavLink to="/products" className={linkClass}>Catalog</NavLink>
          {isAuthenticated ? (
            <button onClick={handleLogout} className="text-sm font-medium text-gray-700 transition hover:text-blue-600">
              Logout
            </button>
          ) : (
            <>
              <NavLink to="/login" className={linkClass}>Login</NavLink>
              <NavLink to="/register" className={linkClass}>Register</NavLink>
            </>
          )}
          <NavLink to="/cart" className="relative" aria-label="Cart">
            <svg className="h-6 w-6 text-gray-700 hover:text-blue-600 transition" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 00-3 3h15.75m-12.75-3h11.218c.51 0 .962-.34 1.09-.837l1.552-6.21A1.125 1.125 0 0017.5 6H6.107M7.5 14.25L5.106 5.272M9.75 18.75a1.125 1.125 0 100 2.25 1.125 1.125 0 000-2.25zm7.5 0a1.125 1.125 0 100 2.25 1.125 1.125 0 000-2.25z" />
            </svg>
            {cartCount > 0 && (
              <span className="absolute -right-2 -top-2 flex h-4 w-4 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                {cartCount}
              </span>
            )}
          </NavLink>
        </div>

        {/* Mobile: cart + hamburger */}
        <div className="flex items-center gap-3 sm:hidden">
          <NavLink to="/cart" className="relative" aria-label="Cart">
            <svg className="h-6 w-6 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 00-3 3h15.75m-12.75-3h11.218c.51 0 .962-.34 1.09-.837l1.552-6.21A1.125 1.125 0 0017.5 6H6.107M7.5 14.25L5.106 5.272M9.75 18.75a1.125 1.125 0 100 2.25 1.125 1.125 0 000-2.25zm7.5 0a1.125 1.125 0 100 2.25 1.125 1.125 0 000-2.25z" />
            </svg>
            {cartCount > 0 && (
              <span className="absolute -right-2 -top-2 flex h-4 w-4 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                {cartCount}
              </span>
            )}
          </NavLink>
          <button onClick={() => setMenuOpen(o => !o)} aria-label="Toggle menu" className="text-gray-700">
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              {menuOpen
                ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />}
            </svg>
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="flex flex-col gap-4 border-t border-gray-200 px-4 py-4 sm:hidden">
          <NavLink to="/products" className={linkClass} onClick={() => setMenuOpen(false)}>Catalog</NavLink>
          {isAuthenticated ? (
            <button onClick={() => { handleLogout(); setMenuOpen(false) }} className="text-left text-sm font-medium text-gray-700">
              Logout
            </button>
          ) : (
            <>
              <NavLink to="/login" className={linkClass} onClick={() => setMenuOpen(false)}>Login</NavLink>
              <NavLink to="/register" className={linkClass} onClick={() => setMenuOpen(false)}>Register</NavLink>
            </>
          )}
        </div>
      )}
    </nav>
  )
}
