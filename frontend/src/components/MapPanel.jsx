import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip } from 'react-leaflet'

const BEIJING = [39.925, 116.395]

function lineCoordinates(geometry) {
  return geometry?.coordinates?.map(([longitude, latitude]) => [latitude, longitude]) ?? []
}

export default function MapPanel({ trajectories = [], hotspots = [], selectedHotspot, onHotspotSelect, focusPoint }) {
  return (
    <div className="map-wrap">
      <MapContainer center={BEIJING} zoom={10} scrollWheelZoom className="map-canvas">
        <TileLayer
          attribution="&copy; 高德地图"
          url="https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
          subdomains={['1', '2', '3', '4']}
        />
        {trajectories.slice(0, 40).map((trajectory) => (
          <Polyline
            key={trajectory.trajectory_id}
            positions={lineCoordinates(trajectory.geometry)}
            pathOptions={{ color: '#000000', weight: 2, opacity: 0.85 }}
          />
        ))}
        {hotspots.map((hotspot) => {
          const active = selectedHotspot?.hotspot_id === hotspot.hotspot_id
          const radius = Math.min(20, Math.max(7, Math.sqrt(hotspot.visit_count) / 2.4))
          return (
            <CircleMarker
              key={hotspot.hotspot_id}
              center={[hotspot.center.latitude, hotspot.center.longitude]}
              radius={active ? radius + 5 : radius}
              eventHandlers={{ click: () => onHotspotSelect?.(hotspot) }}
              pathOptions={{
                color: active ? '#ffb36a' : '#1e3a8a',
                fillColor: active ? '#ffb36a' : '#1e3a8a',
                fillOpacity: active ? 0.8 : 0.7,
                weight: active ? 3 : 1,
              }}
            >
              <Tooltip direction="top" offset={[0, -8]}>
                {hotspot.hotspot_id} · {hotspot.visit_count.toLocaleString()} visits
              </Tooltip>
            </CircleMarker>
          )
        })}
        {focusPoint && focusPoint.latitude != null && focusPoint.longitude != null ? (
          <CircleMarker
            center={[focusPoint.latitude, focusPoint.longitude]}
            radius={10}
            pathOptions={{ color: '#ff2d55', fillColor: '#ff2d55', fillOpacity: 1, weight: 3 }}
          >
            <Tooltip direction="top" offset={[0, -8]}>
              时刻位置 · {focusPoint.latitude.toFixed(4)}, {focusPoint.longitude.toFixed(4)}
            </Tooltip>
          </CircleMarker>
        ) : null}
      </MapContainer>
      <div className="map-legend">
        <span><i className="legend-dot trajectory" />轨迹线</span>
        <span><i className="legend-dot hotspot" />热点中心</span>
        {focusPoint ? <span><i className="legend-dot" style={{ background: '#ff2d55' }} />时刻位置</span> : null}
        <span className="map-coordinates">39.925°N · 116.395°E</span>
      </div>
    </div>
  )
}

