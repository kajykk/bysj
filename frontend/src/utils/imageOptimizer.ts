/**
 * Image optimization utilities for WebP conversion and responsive images.
 */

export interface ImageOptimizationOptions {
  quality?: number
  widths?: number[]
  fallbackFormat?: 'jpeg' | 'png'
}

const DEFAULT_OPTIONS: ImageOptimizationOptions = {
  quality: 85,
  widths: [320, 640, 960, 1280, 1920],
  fallbackFormat: 'jpeg',
}

/**
 * Check if browser supports WebP format.
 */
export function supportsWebP(): boolean {
  const canvas = document.createElement('canvas')
  if (canvas.getContext && canvas.getContext('2d')) {
    return canvas.toDataURL('image/webp').indexOf('data:image/webp') === 0
  }
  return false
}

/**
 * Check if browser supports AVIF format.
 */
export function supportsAVIF(): boolean {
  const canvas = document.createElement('canvas')
  if (canvas.getContext && canvas.getContext('2d')) {
    return canvas.toDataURL('image/avif').indexOf('data:image/avif') === 0
  }
  return false
}

/**
 * Get the best supported image format.
 */
export function getBestImageFormat(): 'avif' | 'webp' | 'jpeg' {
  if (supportsAVIF()) return 'avif'
  if (supportsWebP()) return 'webp'
  return 'jpeg'
}

/**
 * Convert image URL to WebP format.
 * This is a client-side helper; actual conversion should be done server-side or via CDN.
 */
export function toWebPUrl(src: string, quality: number = 85): string {
  // If already webp, return as-is
  if (src.endsWith('.webp')) return src

  // For external URLs or data URLs, return as-is
  if (src.startsWith('http') || src.startsWith('data:')) return src

  // Append webp conversion parameter (for CDN or server-side processing)
  const separator = src.includes('?') ? '&' : '?'
  return `${src}${separator}format=webp&quality=${quality}`
}

/**
 * Generate srcset for responsive images.
 */
export function generateSrcSet(
  src: string,
  options: ImageOptimizationOptions = {},
): string {
  const opts = { ...DEFAULT_OPTIONS, ...options }
  const format = getBestImageFormat()

  return opts.widths!
    .map((width) => {
      const url = `${src}?w=${width}&format=${format}&quality=${opts.quality}`
      return `${url} ${width}w`
    })
    .join(', ')
}

/**
 * Generate picture element sources with format fallbacks.
 */
export function generatePictureSources(
  src: string,
  options: ImageOptimizationOptions = {},
): { srcset: string; type: string }[] {
  const opts = { ...DEFAULT_OPTIONS, ...options }
  const sources: { srcset: string; type: string }[] = []

  // AVIF (best compression)
  if (supportsAVIF()) {
    sources.push({
      srcset: generateSrcSet(src, { ...opts, widths: [opts.widths![0]] }),
      type: 'image/avif',
    })
  }

  // WebP (good compression, wide support)
  if (supportsWebP()) {
    sources.push({
      srcset: generateSrcSet(src, { ...opts, widths: [opts.widths![0]] }),
      type: 'image/webp',
    })
  }

  return sources
}

/**
 * Optimize image file size by compressing on client side.
 * Uses Canvas API for format conversion.
 */
export async function compressImage(
  file: File,
  options: ImageOptimizationOptions = {},
): Promise<Blob> {
  const opts = { ...DEFAULT_OPTIONS, ...options }

  return new Promise((resolve, reject) => {
    const img = new Image()
    const url = URL.createObjectURL(file)

    img.onload = () => {
      URL.revokeObjectURL(url)

      const canvas = document.createElement('canvas')
      canvas.width = img.width
      canvas.height = img.height

      const ctx = canvas.getContext('2d')
      if (!ctx) {
        reject(new Error('Failed to get canvas context'))
        return
      }

      ctx.drawImage(img, 0, 0)

      const format = supportsWebP() ? 'image/webp' : `image/${opts.fallbackFormat}`
      canvas.toBlob(
        (blob) => {
          if (blob) {
            resolve(blob)
          } else {
            reject(new Error('Failed to compress image'))
          }
        },
        format,
        opts.quality! / 100,
      )
    }

    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('Failed to load image'))
    }

    img.src = url
  })
}

/**
 * Get optimal image dimensions based on container width and DPR.
 */
export function getOptimalImageWidth(
  containerWidth: number,
  dpr: number = window.devicePixelRatio || 1,
): number {
  const targetWidth = containerWidth * dpr
  const standardWidths = [320, 640, 960, 1280, 1920, 2560]

  // Find the smallest standard width that is >= target width
  const optimal = standardWidths.find((w) => w >= targetWidth)
  return optimal || standardWidths[standardWidths.length - 1]
}
