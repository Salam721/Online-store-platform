import { useEffect, useMemo, useState } from 'react'
import { getProducts } from '@/api/client'
import ProductCard, { type Product } from '@/components/ProductCard'

export default function Catalog() {
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [category, setCategory] = useState<string>('All')
  const [search, setSearch] = useState('')

  useEffect(() => {
    setLoading(true)
    setError(null)
    getProducts()
      .then(setProducts)
      .catch(e => setError(e.message ?? 'Failed to load products'))
      .finally(() => setLoading(false))
  }, [])

  const categories = useMemo(
    () => ['All', ...Array.from(new Set(products.map(p => p.category))).sort()],
    [products]
  )

  const filtered = useMemo(
    () =>
      products.filter(
        p =>
          (category === 'All' || p.category === category) &&
          p.title.toLowerCase().includes(search.toLowerCase())
      ),
    [products, category, search]
  )

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Products</h1>

      {/* Filters */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center">
        <input
          type="search"
          placeholder="Search products…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="rounded-lg border border-gray-300 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 sm:w-64"
        />
        <div className="flex flex-wrap gap-2">
          {categories.map(cat => (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              className={`rounded-full px-3 py-1 text-sm font-medium transition ${
                category === cat
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="flex justify-center py-16">
          <svg className="h-8 w-8 animate-spin text-blue-600" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
          </svg>
        </div>
      )}

      {error && <p className="py-8 text-center text-red-600">{error}</p>}

      {!loading && !error && filtered.length === 0 && (
        <p className="py-8 text-center text-gray-500">No products found.</p>
      )}

      {!loading && !error && filtered.length > 0 && (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map(p => <ProductCard key={p.id} product={p} />)}
        </div>
      )}
    </main>
  )
}
