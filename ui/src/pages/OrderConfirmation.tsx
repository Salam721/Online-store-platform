import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useCart } from '@/contexts/CartContext'

export default function OrderConfirmation() {
  const { clearCart } = useCart()
  const location = useLocation()
  const orderId = (location.state as { order_id?: string })?.order_id

  useEffect(() => { clearCart() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main className="flex min-h-[calc(100vh-57px)] items-center justify-center px-4 text-center">
      <div className="max-w-sm">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-100">
          <svg className="h-8 w-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-gray-900">Order placed!</h1>
        {orderId && (
          <p className="mt-2 text-sm text-gray-500">
            Order ID: <span className="font-mono font-medium text-gray-900">{orderId}</span>
          </p>
        )}
        <p className="mt-3 text-gray-600">
          Thanks for your order. You'll receive a confirmation email shortly.
        </p>
        <Link to="/products" className="mt-6 inline-block rounded-lg bg-blue-600 px-6 py-2.5 font-semibold text-white transition hover:bg-blue-700">
          Continue shopping
        </Link>
      </div>
    </main>
  )
}
