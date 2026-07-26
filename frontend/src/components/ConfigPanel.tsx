import { useState, useEffect, useRef, useCallback } from 'react';
import type { UserConfig, UserConfigUpdate, CategoryInfo } from '../types';
import { getConfig, updateConfig, getCategories } from '../api/config';
import { formatPercent, formatISKCompact } from '../utils/format';

/** Long enough to coalesce a slider drag, short enough to feel immediate. */
const AUTOSAVE_DELAY_MS = 700;

export function ConfigPanel() {
  const [config, setConfig] = useState<UserConfig | null>(null);
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const savedTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // Skips the write that would otherwise fire on the initial load.
  const loaded = useRef(false);

  useEffect(() => {
    async function load() {
      try {
        const [cfg, cats] = await Promise.all([getConfig(), getCategories()]);
        setConfig(cfg);
        setCategories(cats);
        loaded.current = true;
      } catch {
        setError('Failed to load configuration');
      }
    }
    load();
    return () => {
      clearTimeout(saveTimer.current);
      clearTimeout(savedTimer.current);
    };
  }, []);

  const save = useCallback(async (next: UserConfig) => {
    setSaving(true);
    setError(null);
    try {
      await updateConfig(next as UserConfigUpdate);
      setSaved(true);
      clearTimeout(savedTimer.current);
      savedTimer.current = setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      // Surface the server's reason -- a rejected category ID reads very
      // differently from the request never landing.
      setError(e instanceof Error ? e.message : 'Failed to save configuration');
    } finally {
      setSaving(false);
    }
  }, []);

  /**
   * Every control routes through here so a change is never left sitting in
   * local state. The old panel only wrote on an explicit Save press, while the
   * dashboard's category picker saved on every toggle -- so identical-looking
   * edits persisted in one place and were silently dropped in the other.
   */
  const applyChange = useCallback(
    (patch: Partial<UserConfig>) => {
      setConfig((prev) => {
        if (!prev) return prev;
        const next = { ...prev, ...patch };
        if (loaded.current) {
          clearTimeout(saveTimer.current);
          saveTimer.current = setTimeout(() => save(next), AUTOSAVE_DELAY_MS);
        }
        return next;
      });
    },
    [save]
  );

  const handleSaveNow = () => {
    if (!config) return;
    clearTimeout(saveTimer.current);
    save(config);
  };

  const toggleCategory = (categoryId: number) => {
    if (!config) return;
    const current = config.tracked_category_ids;
    const updated = current.includes(categoryId)
      ? current.filter((id) => id !== categoryId)
      : [...current, categoryId];
    applyChange({ tracked_category_ids: updated });
  };

  if (!config) {
    return <div className="loading">Loading configuration...</div>;
  }

  return (
    <div className="config-panel">
      <h2>Alert Configuration</h2>

      {error && <div className="error-msg">{error}</div>}
      <div className="save-status" aria-live="polite">
        {saving ? 'Saving...' : saved ? 'Saved' : 'Changes save automatically'}
      </div>

      <section className="config-section">
        <h3>Discount Threshold</h3>
        <p className="config-help">
          Only alert when an item is at least this much cheaper than Jita.
        </p>
        <div className="slider-container">
          <input
            type="range"
            min="1"
            max="50"
            value={config.discount_threshold * 100}
            onChange={(e) =>
              applyChange({ discount_threshold: parseInt(e.target.value) / 100 })
            }
            className="threshold-slider"
          />
          <span className="slider-value">
            {formatPercent(config.discount_threshold)}
          </span>
        </div>
      </section>

      <section className="config-section">
        <h3>Minimum Profit per Unit</h3>
        <p className="config-help">
          Only alert if the profit per unit exceeds this amount.
        </p>
        <input
          type="number"
          value={config.min_profit_isk}
          onChange={(e) =>
            applyChange({ min_profit_isk: parseFloat(e.target.value) || 0 })
          }
          className="number-input"
          min="0"
          step="100000"
        />
        <span className="input-hint">{formatISKCompact(config.min_profit_isk)}</span>
      </section>

      <section className="config-section">
        <h3>Minimum Volume Available</h3>
        <p className="config-help">
          Only alert if at least this many units are available.
        </p>
        <input
          type="number"
          value={config.min_volume}
          onChange={(e) =>
            applyChange({ min_volume: parseInt(e.target.value) || 1 })
          }
          className="number-input"
          min="1"
        />
      </section>

      <section className="config-section">
        <h3>Tracked Categories</h3>
        <p className="config-help">
          Select which item categories to monitor for arbitrage opportunities.
        </p>
        <div className="category-grid">
          {categories.map((cat) => (
            <label key={cat.category_id} className="category-checkbox">
              <input
                type="checkbox"
                checked={config.tracked_category_ids.includes(cat.category_id)}
                onChange={() => toggleCategory(cat.category_id)}
              />
              <span>{cat.name}</span>
            </label>
          ))}
        </div>
      </section>

      <section className="config-section">
        <h3>Alert Threshold</h3>
        <p className="config-help">
          A separate, usually stricter bar for what actually notifies you.
          The settings above decide what fills the table; these decide what is
          worth interrupting you for. Alerts only fire for the region you are
          actually in, and the same item won't alert twice within 6 hours.
        </p>
        <div className="slider-container">
          <input
            type="range"
            min="1"
            max="90"
            value={config.alert_discount_threshold * 100}
            onChange={(e) =>
              applyChange({ alert_discount_threshold: parseInt(e.target.value) / 100 })
            }
            className="threshold-slider"
          />
          <span className="slider-value">
            {formatPercent(config.alert_discount_threshold)}
          </span>
        </div>

        <div className="config-subfield">
          <label>
            Min profit per unit
            <input
              type="number"
              value={config.alert_min_profit_isk}
              onChange={(e) =>
                applyChange({ alert_min_profit_isk: parseFloat(e.target.value) || 0 })
              }
              className="number-input"
              min="0"
              step="100000"
            />
          </label>
          <span className="input-hint">
            {formatISKCompact(config.alert_min_profit_isk)}
          </span>
        </div>

        <div className="config-subfield">
          <label>
            Min volume
            <input
              type="number"
              value={config.alert_min_volume}
              onChange={(e) =>
                applyChange({ alert_min_volume: parseInt(e.target.value) || 1 })
              }
              className="number-input"
              min="1"
            />
          </label>
        </div>

        <div className="config-subfield">
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={config.alert_on_blueprints}
              onChange={(e) =>
                applyChange({ alert_on_blueprints: e.target.checked })
              }
            />
            <span>Alert on blueprints</span>
          </label>
        </div>
        <p className="config-help">
          Off by default. EVE gives blueprint originals and copies the same item
          ID, so a cheap copy on sale locally looks like a 90%+ discount against
          an original's Jita price. The deals are real listings but not real
          margins, and they crowd everything else out of your alerts. They still
          appear in the table.
        </p>

        {config.alert_discount_threshold < config.discount_threshold && (
          <p className="config-warning">
            This is looser than the table filter above, so every row shown will
            also alert. Raise it to make alerts more selective than browsing.
          </p>
        )}
      </section>

      <section className="config-section">
        <h3>Notifications</h3>
        <div className="toggle-group">
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={config.notifications_enabled}
              onChange={(e) =>
                applyChange({ notifications_enabled: e.target.checked })
              }
            />
            <span>Browser Notifications</span>
          </label>
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={config.sound_enabled}
              onChange={(e) =>
                applyChange({ sound_enabled: e.target.checked })
              }
            />
            <span>Sound Alert</span>
          </label>
        </div>
      </section>

      <button onClick={handleSaveNow} disabled={saving} className="save-btn">
        {saving ? 'Saving...' : 'Save Now'}
      </button>
    </div>
  );
}
