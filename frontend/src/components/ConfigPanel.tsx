import { useState, useEffect } from 'react';
import type { UserConfig, UserConfigUpdate, CategoryInfo } from '../types';
import { getConfig, updateConfig, getCategories } from '../api/config';
import { formatPercent, formatISKCompact } from '../utils/format';

export function ConfigPanel() {
  const [config, setConfig] = useState<UserConfig | null>(null);
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [cfg, cats] = await Promise.all([getConfig(), getCategories()]);
        setConfig(cfg);
        setCategories(cats);
      } catch (e) {
        setError('Failed to load configuration');
      }
    }
    load();
  }, []);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setSaved(false);
    setError(null);

    try {
      const updated = await updateConfig(config as UserConfigUpdate);
      setConfig(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setError('Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const toggleCategory = (categoryId: number) => {
    if (!config) return;
    const current = config.tracked_category_ids;
    const updated = current.includes(categoryId)
      ? current.filter((id) => id !== categoryId)
      : [...current, categoryId];
    setConfig({ ...config, tracked_category_ids: updated });
  };

  if (!config) {
    return <div className="loading">Loading configuration...</div>;
  }

  return (
    <div className="config-panel">
      <h2>Alert Configuration</h2>

      {error && <div className="error-msg">{error}</div>}
      {saved && <div className="success-msg">Settings saved!</div>}

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
              setConfig({
                ...config,
                discount_threshold: parseInt(e.target.value) / 100,
              })
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
            setConfig({ ...config, min_profit_isk: parseFloat(e.target.value) || 0 })
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
            setConfig({ ...config, min_volume: parseInt(e.target.value) || 1 })
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
        <h3>Notifications</h3>
        <div className="toggle-group">
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={config.notifications_enabled}
              onChange={(e) =>
                setConfig({ ...config, notifications_enabled: e.target.checked })
              }
            />
            <span>Browser Notifications</span>
          </label>
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={config.sound_enabled}
              onChange={(e) =>
                setConfig({ ...config, sound_enabled: e.target.checked })
              }
            />
            <span>Sound Alert</span>
          </label>
        </div>
      </section>

      <button onClick={handleSave} disabled={saving} className="save-btn">
        {saving ? 'Saving...' : 'Save Settings'}
      </button>
    </div>
  );
}
