import type { FetchProgress } from '../types';

const PHASE_LABEL: Record<FetchProgress['phase'], string> = {
  region: 'Reading orders in',
  jita: 'Reading Jita orders',
  compare: 'Comparing prices in',
  nearby: 'Scanning nearby regions --',
};

/**
 * A full Jita pull is ~275 pages and takes several seconds. Showing which
 * region is being read and how far along it is beats an unqualified spinner,
 * which gives no way to tell slow from stuck.
 */
export function FetchProgressBar({ progress }: { progress: FetchProgress }) {
  const { phase, region_name, completed, total } = progress;
  const pct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  const label = PHASE_LABEL[phase] ?? 'Scanning';
  // The jita phase names its own market; the rest carry a region or a count.
  const showsRegion = phase !== 'jita';
  const showsPages = total > 1 && phase !== 'nearby';

  return (
    <div className="fetch-progress" role="status" aria-live="polite">
      <div className="fetch-progress-label">
        <span>
          {label}
          {showsRegion && ` ${region_name}`}
          {showsPages && ` -- page ${completed} of ${total}`}
        </span>
        {total > 1 && <span className="fetch-progress-pct">{pct}%</span>}
      </div>
      <div className="fetch-progress-track">
        <div
          className="fetch-progress-fill"
          style={{ width: `${total > 1 ? pct : 100}%` }}
        />
      </div>
    </div>
  );
}
