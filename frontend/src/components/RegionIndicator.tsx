interface RegionIndicatorProps {
  regionName: string | null;
  characterName: string;
  isConnected: boolean;
}

export function RegionIndicator({ regionName, characterName, isConnected }: RegionIndicatorProps) {
  return (
    <div className="region-indicator">
      <div className="region-info">
        <span className="character-name">{characterName}</span>
        <span className="region-name">
          {regionName ? `Current Region: ${regionName}` : 'Location: Detecting...'}
        </span>
      </div>
      <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
        {isConnected ? 'Live' : 'Reconnecting...'}
      </div>
    </div>
  );
}
