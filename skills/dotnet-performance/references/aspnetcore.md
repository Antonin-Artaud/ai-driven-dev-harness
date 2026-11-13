# ASP.NET Core

| Tier | Rule | When not, pitfalls | Version | Source |
|---|---|---|---|---|
| A | Return large collections in pages, or as `IAsyncEnumerable<T>`; never return a lazy `IEnumerable<T>` from an action. | — | ASP.NET Core 3.0 for `IAsyncEnumerable<T>` | https://learn.microsoft.com/en-us/aspnet/core/fundamentals/best-practices |
| A | Read request bodies asynchronously (`ReadFormAsync`, `JsonSerializer.DeserializeAsync`) and do not load large bodies into memory. | Do not assume `ContentLength` is set. | not stated | https://learn.microsoft.com/en-us/aspnet/core/fundamentals/best-practices |
| A | Keep middleware and per-request code fast; move long work to background services, with `IServiceScopeFactory` instead of captured `HttpContext` or request `DbContext`. | Never store `HttpContext` in a field or use it after the request. | not stated | https://learn.microsoft.com/en-us/aspnet/core/fundamentals/best-practices |
| A | Cache what can be cached (memory, distributed, response caching). | — | not stated | https://learn.microsoft.com/en-us/aspnet/core/fundamentals/best-practices |
| B | Output caching: `AddOutputCache`, `UseOutputCache` after routing and authorization, then a policy (`CacheOutput`, `[OutputCache]`). | Nothing is cached until a policy applies; by default only 200 GET/HEAD, no cookies, no authenticated requests; in-process store unless Redis. | ASP.NET Core 7 (page section) | https://learn.microsoft.com/en-us/aspnet/core/performance/caching/output |
| B | Response compression: prefer the web server's compression (IIS, Apache, Nginx); otherwise `AddResponseCompression`/`UseResponseCompression` with Brotli and Gzip. | `EnableForHttps` exposes dynamic pages to CRIME and BREACH (antiforgery tokens mitigate); do not compress already compressed or tiny files. | not stated | https://learn.microsoft.com/en-us/aspnet/core/performance/response-compression |
