import { useQuery } from '@tanstack/react-query'
import { getEntityProfile, type EntityProfile } from '@/api/v3'

interface Props {
  name: string
  context: string
  /** Source URLs from candidate's evidence — used to harvest og:image previews. */
  evidenceUrls?: string[]
}

function TypePill({ kind }: { kind: EntityProfile['entity_type'] }) {
  const label =
    kind === 'person' ? 'Person'
    : kind === 'place' ? 'Place'
    : kind === 'item'  ? 'Item'
    : kind === 'event' ? 'Event'
    : 'Entity'
  return (
    <span className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-violet-900/40 text-violet-200 font-semibold">
      {label}
    </span>
  )
}

function MapEmbed({
  lat, lng, address, nameEn, nameNative,
}: {
  lat: number
  lng: number
  address?: string
  nameEn?: string
  nameNative?: string | null
}) {
  // OpenStreetMap embed needs a bbox. Pick a small window around the point.
  const d = 0.01
  const bbox = `${lng - d}%2C${lat - d}%2C${lng + d}%2C${lat + d}`
  const marker = `${lat}%2C${lng}`
  const src = `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${marker}`
  return (
    <div className="space-y-1">
      <iframe
        src={src}
        title="map"
        className="w-full h-48 rounded border border-border"
        loading="lazy"
      />
      {(nameNative || nameEn) && (
        <p className="text-[12px] font-medium text-foreground leading-tight">
          {nameNative ?? nameEn}
          {nameNative && nameEn && nameNative !== nameEn && (
            <span className="ml-1.5 text-[10px] font-normal text-muted-foreground">· {nameEn}</span>
          )}
        </p>
      )}
      {address && <p className="text-[11px] text-foreground/80">{address}</p>}
      <p className="text-[9px] text-muted-foreground tabular-nums">
        {lat.toFixed(5)}, {lng.toFixed(5)}
      </p>
    </div>
  )
}

function ImageGallery({ images }: { images: EntityProfile['images'] }) {
  if (!images?.length) return null
  return (
    <div className="grid grid-cols-3 gap-1.5">
      {images.slice(0, 6).map((img, i) => (
        <a key={i} href={img.url} target="_blank" rel="noopener noreferrer"
           className="block bg-card/40 border border-border rounded overflow-hidden hover:border-violet-700 transition-colors"
           title={img.alt || ''}>
          <img
            src={img.url}
            alt={img.alt ?? ''}
            loading="lazy"
            className="w-full h-24 object-cover"
            onError={(e) => { (e.target as HTMLImageElement).parentElement!.style.display = 'none' }}
          />
        </a>
      ))}
    </div>
  )
}

function LinkChip({ label, url, kind }: { label: string; url: string; kind: 'social' | 'official' }) {
  return (
    <a href={url} target="_blank" rel="noopener noreferrer"
       className={
         'inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded border transition-colors no-underline ' +
         (kind === 'social'
           ? 'border-sky-800/50 bg-sky-950/30 text-sky-200 hover:bg-sky-900/40'
           : 'border-emerald-800/50 bg-emerald-950/20 text-emerald-200 hover:bg-emerald-900/40')
       }>
      <span className="opacity-70">{kind === 'social' ? '#' : '↗'}</span>
      {label}
    </a>
  )
}

export function EntityProfileCard({ name, context, evidenceUrls }: Props) {
  // Key only by name+context — evidence_urls are an input but not a cache axis.
  // Same entity in different runs with different evidence is still the same entity.
  const urlsKey = (evidenceUrls ?? []).slice(0, 6).sort().join('|')
  const { data, isLoading, isError } = useQuery({
    queryKey: ['entity-profile', name, context, urlsKey],
    queryFn: () => getEntityProfile(name, context, evidenceUrls ?? []),
    enabled: !!name,
    staleTime: 30 * 60 * 1000,
    retry: 0,
  })

  if (isLoading) {
    return (
      <div className="rounded-md border border-border bg-card/40 px-3 py-3">
        <p className="text-[11px] text-muted-foreground italic">Loading profile for {name}…</p>
      </div>
    )
  }
  if (isError || !data) {
    return null
  }

  const hasAnything =
    (data.images?.length ?? 0) > 0 ||
    (data.links?.social?.length ?? 0) > 0 ||
    (data.links?.official?.length ?? 0) > 0 ||
    !!data.geo

  if (!hasAnything) return null

  return (
    <div className="rounded-md border border-violet-900/30 bg-violet-950/10 px-3 py-3 space-y-3">
      <div className="flex items-center gap-2">
        <TypePill kind={data.entity_type} />
        <span className="text-xs font-semibold text-foreground">{name}</span>
      </div>

      {data.geo && (
        <MapEmbed
          lat={data.geo.lat}
          lng={data.geo.lng}
          address={data.geo.address}
          nameEn={data.geo.name_en}
          nameNative={data.geo.name_native ?? null}
        />
      )}

      <ImageGallery images={data.images ?? []} />

      {(data.links?.social?.length || data.links?.official?.length) ? (
        <div className="flex flex-wrap gap-1.5">
          {data.links.official.map((l, i) => (
            <LinkChip key={`o-${i}`} label={l.label} url={l.url} kind="official" />
          ))}
          {data.links.social.map((l, i) => (
            <LinkChip key={`s-${i}`} label={l.platform} url={l.url} kind="social" />
          ))}
        </div>
      ) : null}
    </div>
  )
}
