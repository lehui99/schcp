检查SSL历史证书防止SSL劫持的透明代理
======

问与答
-----
1. 问：如何使用？<br />答：编辑config.json，填写上级代理的IP地址、端口和类型。之后启动scphcp.bat（Windows）或scphcp.sh（Linux）。之后设置浏览器代理即可。
2. 问：scphcp是什么类型的代理？HTTP代理还是SOCKS代理？<br />答：取决于config.json中的parentProxyType。如果是none或socks，则是socks代理；如果是connect，则是https代理。
3. 问：parentProxyType中的none和socks有什么区别？<br />答：none表示不使用上级代理，scphcp会直连目标https网站；socks表示使用上级socks代理连接目标https网站。


SSL Certification History Check Proxy
======
