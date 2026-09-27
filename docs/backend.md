# 后端适配依据

复旦图书馆首页将“资源发现”链接到 `https://fudan-primo.hosted.exlibrisgroup.com.cn/primo-explore/search?vid=fdu`。

2026-09-27 通过独立匿名 HTTP 请求验证以下流程（不从浏览器获取令牌）：

1. `GET /primo_library/libweb/webservices/rest/v1/guestJwt/FDU?vid=fdu&lang=zh_CN` 获取访客令牌。
2. 使用 `Authorization: Bearer <guest JWT>` 请求下列只读服务。
3. `GET /primo_library/libweb/webservices/rest/primo-explore/v1/pnxs` 检索，`q` 指定字段、匹配方式和检索词。
4. `GET /primo_library/libweb/webservices/rest/primo-explore/v1/pnxs/{context}/{record_id}` 获取详情。
5. `GET /primo_library/libweb/webservices/rest/v1/configuration/fdu` 确认公开视图配置。

机构参数 `inst=FDU`，视图参数 `vid=fdu`。从实际配置核实的检索范围为：

| 对外 scope | tab | 后端 scope |
| --- | --- | --- |
| articles | digital_tab | article_scope |
| all | default_tab | default_scope |
| books_journals | book_journal | book_journal |

全文检索通过文档规定的 `ftext` 字段实现。在此部署上，单独传递 `searchInFulltextUserSelection=true/false` 没有改变测试结果，不能用该参数冒充全文检索。程序明确发送 `q=ftext,contains,...`，在线测试同时验证不同结果集及无匹配检索返回零结果。

`pcAvailability` 控制是否扩大到无全文的记录，与 `ftext` 是两个维度。为 `full_text_available_only=true` 同时添加 `facet_tlevel,exact,online_resources`，并令 `pcAvailability=false`。

上游结果 `info.errorDetails` 可能表示部分结果，即使 HTTP 是 200。程序保留已有结果、返回 `partial=true` 和警告，不把它当完整结果或存入成功缓存。详情解析只把 `addata.abstract` 标为明确摘要，`display.description`、`display.snippet` 单独保留。

公开链接仅返回给客户端，服务端不会跟随链接访问出版商。所有后端路径使用固定复旦域名与经过验证的记录 ID 构造；不提供任意 URL 抓取能力。令牌、配置中的无关字段和原始响应不会作为工具结果输出。

## 主要参考

- [复旦大学图书馆首页](https://library.fudan.edu.cn/index.psp)：资源发现入口。
- [Ex Libris Primo Search API](https://developers.exlibrisgroup.com/primo/apis/docs/primoSearch/R0VUIC9wcmltby92MS9zZWFyY2g%3D/)：Primo Classic 检索路径、查询与分面参数。
- [Ex Libris Guest JWT API](https://developers.exlibrisgroup.com/primo/apis/docs/primoJwt/R0VUIC9wcmltby92MS9qd3Qve2luc3RpdHV0aW9ufQ%3D%3D/)：匿名令牌与 Bearer 用法。
- [Ex Libris Brief Search](https://developers.exlibrisgroup.com/primo/apis/webservices/xservices/search/briefsearch/)：字段 `ftext`、`abstract` 等及分页范围。此项目不调用受 IP 限制的 XService。
- [Ex Libris Search Output](https://developers.exlibrisgroup.com/primo/apis/search-output/)：PNX 结果结构。
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)：使用锁定的 1.x FastMCP 与 stdio 客户端，不依赖 2.x API。
