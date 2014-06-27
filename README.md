检查SSL历史证书防止SSL劫持的透明代理
======

scphcp是为了防止证书颁发机构出现问题（比如被黑客入侵、或者迫于某种压力颁发了假证书）的代理工具，只要将浏览器的代理设置为scphcp提供的代理，即可防止SSL劫持。由于scphcp是代理服务器，所以可以跨浏览器使用，不像浏览器插件那样只能在固定的某个浏览器中使用。

问与答
-----
1. 问：如何使用？<br />答：编辑config.json，填写上级代理的IP地址、端口和类型。之后启动scphcp.bat（Windows）或scphcp.sh（Linux）。之后设置浏览器代理即可，端口是config.json中的proxyPort。
2. 问：scphcp是什么类型的代理？HTTP代理还是SOCKS代理？<br />答：取决于config.json中的parentProxyType。如果是none或socks，则是socks代理；如果是connect，则是https代理。
3. 问：parentProxyType中的none和socks有什么区别？<br />答：none表示不使用上级代理，scphcp会直连目标https网站；socks表示使用上级socks代理连接目标https网站。
4. 问：是如何防止SSL劫持的？<br />答：首次访问某个https网站时，scphcp会将此网站的SSL证书保存在config.json中certFilename指定的文件中。之后再次访问此网站，scphcp会将此次网络传输中证书和保存在文件中的证书进行比对，如不同则会直接断开连接。
5. 问：SSL不是端到端加密的吗？scphcp是怎么取得证书的？<br />答：SSL在握手时的数据传输是明文的，之后的数据才是加密的，而SSL证书是在握手过程中传输的。

SSL Certification History Check Proxy
======
