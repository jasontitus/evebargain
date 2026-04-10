import type { ArbitrageResult, Alert } from '../types';
import { formatISK, formatISKCompact, formatPercent, timeAgo } from '../utils/format';

interface AlertCardProps {
  deal: ArbitrageResult | Alert;
  onDismiss?: (id: number) => void;
}

export function AlertCard({ deal, onDismiss }: AlertCardProps) {
  const isAlert = 'id' in deal;
  const discount = 'discount_pct' in deal ? deal.discount_pct : 0;
  const profit = 'profit_per_unit' in deal ? deal.profit_per_unit : ('potential_profit' in deal ? deal.potential_profit : 0);

  return (
    <div className={`alert-card ${discount >= 0.2 ? 'high-value' : ''}`}>
      <div className="alert-header">
        <span className="item-name">{deal.type_name}</span>
        <span className="discount-badge">{formatPercent(discount)} off</span>
      </div>
      <div className="alert-prices">
        <div className="price-row">
          <span className="price-label">Local:</span>
          <span className="price-value local">{formatISK(deal.local_price)}</span>
        </div>
        <div className="price-row">
          <span className="price-label">Jita:</span>
          <span className="price-value jita">{formatISK(deal.jita_price)}</span>
        </div>
        <div className="price-row">
          <span className="price-label">Profit:</span>
          <span className="price-value profit">{formatISKCompact(profit)}/unit</span>
        </div>
      </div>
      <div className="alert-footer">
        <span className="region-tag">{deal.region_name}</span>
        {'volume_available' in deal && (
          <span className="volume-tag">{deal.volume_available} available</span>
        )}
        {isAlert && 'created_at' in deal && (
          <span className="time-tag">{timeAgo((deal as Alert).created_at)}</span>
        )}
        {isAlert && onDismiss && (
          <button
            className="dismiss-btn"
            onClick={() => onDismiss((deal as Alert).id)}
          >
            Dismiss
          </button>
        )}
      </div>
    </div>
  );
}
