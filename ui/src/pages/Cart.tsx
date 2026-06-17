import { Link, useNavigate } from 'react-router-dom'
import { useCart } from '@/contexts/CartContext'

const fmt = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export default function Cart() {
  const { items, removeItem, updateQuantity, total } = useCart()
  const navigate = useNavigate()

  if (items.length === 0) return (
    <main className="mx-auto max-w-3xl px-4 py-16 text-center">
      <p className="text-gray-500">Your cart is empty.</p>
      <Link to="/products" className="mt-4 inline-block text-blue-600 hover:underline">Browse products</Link>
    </main>
  )

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Your Cart</h1>

      <ul className="divide-y divide-gray-200 rounded-xl border border-gray-200 bg-white">
        {items.map(item => (
          <li key={item.productId} className="flex items-center gap-4 p-4">
            <div className="h-16 w-16 flex-shrink-0 overflow-hidden rounded-lg bg-gray-100">
              {item.imageUrl
                ? <img src={item.imageUrl} alt={item.title} className="h-full w-full object-cover" />
                : <div className="flex h-full items-center justify-center text-gray-400 text-xs">No img</div>
              }
            </div>

            <div className="flex flex-1 flex-col gap-1">
              <p className="font-medium text-gray-900">{item.title}</p>
              <p className="text-sm text-gray-500">{fmt.format(item.price)} each</p>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => item.quantity > 1 ? updateQuantity(item.productId, item.quantity - 1) : removeItem(item.productId)}
                className="h-7 w-7 rounded border border-gray-300 text-gray-600 hover:bg-gray-50"
                aria-label="Decrease quantity"
              >−</button>
              <span className="w-6 text-center text-sm font-medium">{item.quantity}</span>
              <button
                onClick={() => updateQuantity(item.productId, item.quantity + 1)}
                className="h-7 w-7 rounded border border-gray-300 text-gray-600 hover:bg-gray-50"
                aria-label="Increase quantity"
              >+</button>
            </div>

            <p className="w-20 text-right text-sm font-semibold text-gray-900">
              {fmt.format(item.price * item.quantity)}
            </p>

            <button
              onClick={() => removeItem(item.productId)}
              className="text-gray-400 hover:text-red-500 transition"
              aria-label="Remove"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </li>
        ))}
      </ul>

      <div className="mt-6 flex items-center justify-between">
        <p className="text-lg font-bold text-gray-900">Total: {fmt.format(total)}</p>
        <button
          onClick={() => navigate('/checkout')}
          className="rounded-lg bg-blue-600 px-6 py-2.5 font-semibold text-white transition hover:bg-blue-700"
        >
          Checkout
        </button>
      </div>
    </main>
  )
}
