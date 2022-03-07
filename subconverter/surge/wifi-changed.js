const WIFI_DONT_NEED_PROXYS = ['NETGEAR_5G','NETGEAR','ASUS_b'];
const WIFI_NEED_AUTH = ['OoO','nancal','ASUS_b'];
const CURRENT_WIFI_SSID_KEY = 'current_wifi_ssid';

if (wifiChanged()) {
  if(WIFI_NEED_AUTH.includes($network.wifi.ssid)){
    //先关掉代理(使用direct模式)
    $surge.setOutboundMode('direct');
    //进行网络认证
    $httpClient.post({
      url: "http://www.example.com/?opr=pwdLogin&userName=dongjq&pwd=123456&rememberPwd=1",
    },(res,data) => {
      $notification.post(
        'Surge',
        `123`,
        `${data}`
      );
    })
  }
  const mode = WIFI_DONT_NEED_PROXYS.includes($network.wifi.ssid) ? 'direct' : 'rule';
  $surge.setOutboundMode(mode);
  $notification.post(
    'Surge',
    `网络切换为 ${$network.wifi.ssid || '蜂窝'}`,
    `使用 ${mode === 'direct' ? '直接链接':'规则模式' }`
  );
}

function wifiChanged() {
  const currentWifiSSid = $persistentStore.read(CURRENT_WIFI_SSID_KEY);
  const changed = currentWifiSSid !== $network.wifi.ssid;
  changed && $persistentStore.write($network.wifi.ssid, CURRENT_WIFI_SSID_KEY);
  return changed;
}

$done();
