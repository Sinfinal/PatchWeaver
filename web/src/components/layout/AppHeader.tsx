import { useUiStore } from "../../store/uiStore";
import { getApiBase } from "../../services/http";

export function AppHeader(): JSX.Element {
  const autoRefresh = useUiStore((state) => state.autoRefresh);
  const refreshIntervalSec = useUiStore((state) => state.refreshIntervalSec);
  const setAutoRefresh = useUiStore((state) => state.setAutoRefresh);

  return (
    <div className="pw-topbar">
      <div>
        <h2 className="pw-title">PatchWeaver Console</h2>
        <p className="pw-subtitle">控制面、展示面、运维面共用同一套 Python 服务层</p>
      </div>
      <div className="pw-btn-row">
        <span className="pw-chip">API: {getApiBase()}</span>
        <span className="pw-chip">自动刷新: {autoRefresh ? `${refreshIntervalSec}s` : "关闭"}</span>
        <button className="pw-btn" onClick={() => setAutoRefresh(!autoRefresh)} type="button">
          {autoRefresh ? "暂停刷新" : "恢复刷新"}
        </button>
      </div>
    </div>
  );
}
