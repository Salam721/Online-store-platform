import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getProduct } from '@/api/client'
import { useCart } from '@/contexts/CartContext'
import type { Product } from '@/components/ProductCard'

const fmt = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export default function ProductDetail() {
  const { id } = useParams<{ id: string }>()
  const { addItem } = useCart()
  const [product, setProduct] = useState<Product | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [quantity, setQuantity] = useState(1)
  const [added, setAdded] = useState(false)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    setError(null)
    getProduct(id)
      .then(setProduct)
      .catch(e => setError(e.status === 404 ? 'Product not found.' : (e.message ?? 'Failed to load product')))
      .finally(() => setLoading(false))
  }, [id])

  function handleAdd() {
    if (!product) return
    addItem(product, quantity)
    setAdded(true)
    setTimeout(() => setAdded(false), 2000)
  }

  if (loading) return (
    <div className="flex justify-center py-16">
      <svg className="h-8 w-8 animate-spin text-blue-600" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
      </svg>
    </div>
  )

  if (error || !product) return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <Link to="/products" className="text-blue-600 hover:underline">← Back to products</Link>
      <p className="mt-4 text-red-600">{error ?? 'Product not found.'}</p>
    </main>
  )

  const showPlaceholder = !product.image_url

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <Link to="/products" className="text-sm text-blue-600 hover:underline">← Back to products</Link>
      <div className="mt-6 grid grid-cols-1 gap-8 md:grid-cols-2">
        <div className="aspect-square overflow-hidden rounded-xl bg-gray-100">
          {showPlaceholder ? (
            <div className="flex h-full items-center justify-center text-gray-400">
              <svg className="h-20 w-20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M2.25 18.75A2.25 2.25 0 004.5 21h15a2.25 2.25 0 002.25-2.25V5.25A2.25 2.25 0 0019.5 3h-15a2.25 2.25 0 00-2.25 2.25v13.5z" />
              </svg>
            </div>
          ) : (
            <img src={product.image_url} alt={product.title} className="h-full w-full object-cover" />
          )}
        </div>

        <div className="flex flex-col">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{product.category}</p>
          <h1 className="mt-1 text-2xl font-bold text-gray-900">{product.title}</h1>
          <p className="mt-3 text-gray-600">{product.description}</p>
          <p className="mt-4 text-2xl font-bold text-gray-900">{fmt.format(product.price)}</p>

          <div className="mt-6 flex items-center gap-3">
            <label htmlFor="qty" className="text-sm font-medium text-gray-700">Qty</label>
            <div className="flex items-center rounded-lg border border-gray-300">
              <button
                onClick={() => setQuantity(q => Math.max(1, q - 1))}
                className="px-3 py-1.5 text-gray-600 hover:bg-gray-50"
                aria-label="Decrease"
              >−</button>
              <span id="qty" className="min-w-[2.5rem] text-center text-sm font-medium">{quantity}</span>
              <button
                onClick={() => setQuantity(q => q + 1)}
                className="px-3 py-1.5 text-gray-600 hover:bg-gray-50"
                aria-label="Increase"
              >+</button>
            </div>
          </div>

          <button
            onClick={handleAdd}
            className="mt-6 rounded-lg bg-blue-600 px-6 py-3 font-semibold text-white transition hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
          >
            {added ? 'Added to cart ✓' : 'Add to cart'}
          </button>
        </div>
      </div>
    </main>
  )
}
