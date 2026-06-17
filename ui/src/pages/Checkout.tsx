import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { placeOrder } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useCart } from '@/contexts/CartContext'

const fmt = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

interface Address {
  street: string; city: string; state: string; zip: string; country: string
}

export default function Checkout() {
  const { sub } = useAuth()
  const { items, total, clearCart } = useCart()
  const navigate = useNavigate()

  const [address, setAddress] = useState<Address>({ street: '', city: '', state: '', zip: '', country: '' })
  const [paymentMethod, setPaymentMethod] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  function update(field: keyof Address) {
    return (e: React.ChangeEvent<HTMLInputElement>) => setAddress(a => ({ ...a, [field]: e.target.value }))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await placeOrder({
        customer_id: sub!,
        items: items.map(i => ({ productId: i.productId, title: i.title, price: i.price, quantity: i.quantity })),
        total_amount: total,
        shipping_address: address,
        payment_method: paymentMethod,
      })
      clearCart()
      navigate('/orders/confirmation', { state: { order_id: res.order_id } })
    } catch (err: unknown) {
      setError((err as { message?: string }).message ?? 'Failed to place order.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Checkout</h1>

      {/* Order summary */}
      <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4">
        <h2 className="mb-3 font-semibold text-gray-900">Order summary</h2>
        <ul className="divide-y divide-gray-100">
          {items.map(i => (
            <li key={i.productId} className="flex justify-between py-2 text-sm">
              <span className="text-gray-700">{i.title} × {i.quantity}</span>
              <span className="font-medium text-gray-900">{fmt.format(i.price * i.quantity)}</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 flex justify-between font-bold text-gray-900">
          <span>Total</span><span>{fmt.format(total)}</span>
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <h2 className="font-semibold text-gray-900">Shipping address</h2>
        {(['street', 'city', 'state', 'zip', 'country'] as const).map(field => (
          <div key={field}>
            <label htmlFor={field} className="mb-1 block text-sm font-medium capitalize text-gray-700">{field}</label>
            <input
              id={field} type="text" required
              value={address[field]} onChange={update(field)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        ))}

        <div>
          <label htmlFor="payment" className="mb-1 block text-sm font-medium text-gray-700">Payment method</label>
          <input
            id="payment" type="text" required placeholder="e.g. Visa ending in 4242"
            value={paymentMethod} onChange={e => setPaymentMethod(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="submit" disabled={loading || items.length === 0}
          className="rounded-lg bg-blue-600 py-2.5 font-semibold text-white transition hover:bg-blue-700 disabled:opacity-60"
        >
          {loading ? 'Placing order…' : 'Place order'}
        </button>
      </form>
    </main>
  )
}
