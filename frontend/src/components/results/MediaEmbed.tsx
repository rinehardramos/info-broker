/**
 * MediaEmbed — pattern-matches social/video/audio URLs and renders an inline
 * iframe player. Used by EvidenceModal to upgrade text-only evidence URLs
 * into actual visual evidence (the tweet, the YouTube video, the Spotify
 * track, etc.) without any backend round-trip.
 *
 * Returns null when the URL doesn't match a known platform — callers fall
 * through to a regular OpenGraph card.
 */

type EmbedKind =
  | { kind: 'youtube';    id: string }
  | { kind: 'vimeo';      id: string }
  | { kind: 'spotify';    kindParam: 'track' | 'album' | 'playlist' | 'episode' | 'show'; id: string }
  | { kind: 'soundcloud'; url: string }
  | { kind: 'twitter';    id: string }
  | { kind: 'instagram';  id: string }
  | { kind: 'tiktok';     id: string }

const YT_HOSTS = new Set(['youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'])

function detect(rawUrl: string): EmbedKind | null {
  let u: URL
  try { u = new URL(rawUrl) } catch { return null }
  const host = u.hostname.toLowerCase()
  const path = u.pathname

  // YouTube
  if (YT_HOSTS.has(host)) {
    if (host === 'youtu.be') {
      const id = path.replace(/^\//, '').split('/')[0]
      return id ? { kind: 'youtube', id } : null
    }
    const v = u.searchParams.get('v')
    if (v) return { kind: 'youtube', id: v }
    const shorts = path.match(/^\/shorts\/([^/?]+)/)
    if (shorts) return { kind: 'youtube', id: shorts[1] }
    const embed = path.match(/^\/embed\/([^/?]+)/)
    if (embed) return { kind: 'youtube', id: embed[1] }
    return null
  }

  // Vimeo
  if (host === 'vimeo.com' || host === 'player.vimeo.com') {
    const m = path.match(/\/(\d+)/)
    if (m) return { kind: 'vimeo', id: m[1] }
    return null
  }

  // Spotify
  if (host === 'open.spotify.com') {
    const m = path.match(/^\/(track|album|playlist|episode|show)\/([^/?]+)/)
    if (m) return { kind: 'spotify', kindParam: m[1] as 'track', id: m[2] }
    return null
  }

  // SoundCloud
  if (host === 'soundcloud.com' || host === 'm.soundcloud.com') {
    return { kind: 'soundcloud', url: rawUrl }
  }

  // Twitter / X
  if (host === 'twitter.com' || host === 'x.com' || host === 'www.twitter.com' || host === 'www.x.com') {
    const m = path.match(/\/status\/(\d+)/)
    if (m) return { kind: 'twitter', id: m[1] }
    return null
  }

  // Instagram
  if (host === 'www.instagram.com' || host === 'instagram.com') {
    const m = path.match(/^\/(?:p|reel|tv)\/([^/?]+)/)
    if (m) return { kind: 'instagram', id: m[1] }
    return null
  }

  // TikTok
  if (host.endsWith('tiktok.com')) {
    const m = path.match(/\/video\/(\d+)/)
    if (m) return { kind: 'tiktok', id: m[1] }
    return null
  }

  return null
}

/** Returns true if the URL points to an embeddable platform. */
export function isEmbeddable(url: string | undefined | null): boolean {
  if (!url) return false
  return detect(url) !== null
}

function Iframe({
  src,
  title,
  aspect = '16 / 9',
  allow,
  scrolling,
}: {
  src: string
  title: string
  aspect?: string
  allow?: string
  scrolling?: string
}) {
  return (
    <div
      className="w-full overflow-hidden rounded border border-border bg-black/30"
      style={{ aspectRatio: aspect }}
    >
      <iframe
        src={src}
        title={title}
        loading="lazy"
        allow={allow}
        scrolling={scrolling}
        referrerPolicy="strict-origin-when-cross-origin"
        allowFullScreen
        className="w-full h-full border-0"
      />
    </div>
  )
}

export function MediaEmbed({ url }: { url: string }) {
  const target = detect(url)
  if (!target) return null

  switch (target.kind) {
    case 'youtube':
      return (
        <Iframe
          src={`https://www.youtube.com/embed/${encodeURIComponent(target.id)}`}
          title="YouTube"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        />
      )
    case 'vimeo':
      return (
        <Iframe
          src={`https://player.vimeo.com/video/${encodeURIComponent(target.id)}`}
          title="Vimeo"
          allow="autoplay; fullscreen; picture-in-picture"
        />
      )
    case 'spotify':
      return (
        <Iframe
          src={`https://open.spotify.com/embed/${target.kindParam}/${encodeURIComponent(target.id)}`}
          title="Spotify"
          aspect={target.kindParam === 'track' ? 'auto' : '4 / 5'}
          allow="encrypted-media; clipboard-write; picture-in-picture"
        />
      )
    case 'soundcloud':
      return (
        <Iframe
          src={`https://w.soundcloud.com/player/?url=${encodeURIComponent(target.url)}&color=%23a78bfa&visual=true`}
          title="SoundCloud"
          aspect="16 / 9"
          scrolling="no"
        />
      )
    case 'twitter':
      // Twitter's undocumented but stable embed iframe — bypasses widgets.js.
      // Theme follows the host page; we force dark for our dark UI.
      return (
        <Iframe
          src={`https://platform.twitter.com/embed/Tweet.html?id=${encodeURIComponent(target.id)}&theme=dark&dnt=true`}
          title="Tweet"
          aspect="auto"
        />
      )
    case 'instagram':
      return (
        <Iframe
          src={`https://www.instagram.com/p/${encodeURIComponent(target.id)}/embed/`}
          title="Instagram"
          aspect="4 / 5"
          scrolling="no"
        />
      )
    case 'tiktok':
      return (
        <Iframe
          src={`https://www.tiktok.com/embed/v2/${encodeURIComponent(target.id)}`}
          title="TikTok"
          aspect="9 / 16"
        />
      )
  }
}
