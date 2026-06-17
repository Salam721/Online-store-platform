import { useState } from 'react'
import { Link } from 'react-router-dom'

export interface Product {
  id: string
  title: string
  category: string
  description: string
  price: number
  image_url?: string
}

interface ProductCardProps {
  product: Product
}

const priceFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

/**
 * ProductCard — displays a product's image (with grey placeholder fallback),
 * title, category, and price. Clicking the card navigates to `/products/:id`.
 */
export default function ProductCard({ product }: ProductCardProps) {
  const { id, title, category, price, image_url } = product
  const [imageFailed, setImageFailed] = useState(false)
  const showPlaceholder = !image_url || imageFailed

  return (
    <Link
      to={`/products/${id}`}
      className="group flex flex-col overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm transition hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
    >
      <div className="aspect-square w-full overflow-hidden bg-gray-200">
        {showPlaceholder ? (
          <div
            className="flex h-full w-full items-center justify-center bg-gray-200 text-gray-400"
            role="img"
            aria-label={`${title} — no image available`}
          >
            <svg
              className="h-12 w-12"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M2.25 18.75A2.25 2.25 0 004.5 21h15a2.25 2.25 0 002.25-2.25V5.25A2.25 2.25 0 0019.5 3h-15a2.25 2.25 0 00-2.25 2.25v13.5z"
              />
            </svg>
          </div>
        ) : (
          <img
            src={image_url}
            alt={title}
            loading="lazy"
            onError={() => setImageFailed(true)}
            className="h-full w-full object-cover transition group-hover:scale-105"
          />
        )}
      </div>

      <div className="flex flex-1 flex-col gap-1 p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
          {category}
        </p>
        <h3 className="line-clamp-2 text-sm font-semibold text-gray-900">
          {title}
        </h3>
        <p className="mt-auto pt-2 text-base font-bold text-gray-900">
          {priceFormatter.format(price)}
        </p>
      </div>
    </Link>
  )
}
