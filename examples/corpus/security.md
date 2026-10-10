# Atlas 本地部署
前端监听 127.0.0.1:5173，后端监听 127.0.0.1:8000。应用为本地单用户模式，不提供登录认证，不支持直接暴露公网。

# Credentials
API credentials stay in a local configuration file excluded by Git. The UI displays masked keys. Error responses must not echo provider response bodies or secret credentials.
