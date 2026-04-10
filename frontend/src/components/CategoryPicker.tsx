import { useState, useEffect } from 'react';
import type { UserConfig, CategoryInfo } from '../types';
import { getConfig, updateConfig, getCategories } from '../api/config';

interface CategoryPickerProps {
  onConfigChange?: (config: UserConfig) => void;
}

export function CategoryPicker({ onConfigChange }: CategoryPickerProps) {
  const [config, setConfig] = useState<UserConfig | null>(null);
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const [cfg, cats] = await Promise.all([getConfig(), getCategories()]);
        setConfig(cfg);
        setCategories(cats);
      } catch {
        // Non-critical widget
      }
    }
    load();
  }, []);

  const toggleCategory = async (categoryId: number) => {
    if (!config) return;
    const current = config.tracked_category_ids;
    const updated = current.includes(categoryId)
      ? current.filter((id) => id !== categoryId)
      : [...current, categoryId];

    const newConfig = { ...config, tracked_category_ids: updated };
    setConfig(newConfig);

    // Auto-save on toggle
    setSaving(true);
    try {
      const saved = await updateConfig({ tracked_category_ids: updated });
      setConfig(saved);
      onConfigChange?.(saved);
    } catch {
      // Revert on failure
      setConfig(config);
    } finally {
      setSaving(false);
    }
  };

  if (!config || categories.length === 0) return null;

  const trackedNames = categories
    .filter((c) => config.tracked_category_ids.includes(c.category_id))
    .map((c) => c.name);

  return (
    <div className="category-picker">
      <button
        className="category-picker-toggle"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="category-picker-label">
          Tracking: {trackedNames.length === 0
            ? 'No categories selected'
            : trackedNames.join(', ')}
        </span>
        <span className="category-picker-arrow">{expanded ? '\u25B2' : '\u25BC'}</span>
      </button>

      {expanded && (
        <div className="category-picker-dropdown">
          <p className="category-picker-help">
            Select item categories to monitor for deals. Changes save automatically.
          </p>
          <div className="category-picker-grid">
            {categories.map((cat) => (
              <label key={cat.category_id} className="category-picker-item">
                <input
                  type="checkbox"
                  checked={config.tracked_category_ids.includes(cat.category_id)}
                  onChange={() => toggleCategory(cat.category_id)}
                  disabled={saving}
                />
                <span>{cat.name}</span>
              </label>
            ))}
          </div>
          {saving && <p className="category-picker-saving">Saving...</p>}
        </div>
      )}
    </div>
  );
}
