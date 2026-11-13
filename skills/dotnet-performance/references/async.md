# Async

| Tier | Rule | When not, pitfalls | Version | Source |
|---|---|---|---|---|
| A | Async all the way for I/O and data access; never block with `Task.Wait` or `Task<T>.Result`; do not wrap sync APIs in `Task.Run`, do not `Task.Run` then await immediately. | `async void` only for event handlers, never in ASP.NET Core code. | not stated | https://learn.microsoft.com/en-us/aspnet/core/fundamentals/best-practices |
| A | Inside an async method, call the async overloads (analyzer CA1849). | — | not stated | https://github.com/dotnet/docs/blob/main/docs/fundamentals/code-analysis/quality-rules/performance-warnings.md |
| A | `HttpClient` through `IHttpClientFactory` (`AddHttpClient`): manual handler lifetimes cause socket exhaustion and miss DNS changes. | Factory clients are short-lived: do not capture typed clients in singletons; cookie-based apps are advised against the factory. | ASP.NET Core 2.1 | https://learn.microsoft.com/en-us/dotnet/core/extensions/httpclient-factory |
| A | Stream large result sets with `IAsyncEnumerable<T>` and `await foreach`; pass cancellation with `WithCancellation` and `[EnumeratorCancellation]`. | — | .NET Core 3.0 | https://learn.microsoft.com/en-us/dotnet/csharp/asynchronous-programming/generate-consume-asynchronous-stream |
| A | Do not use exceptions for control flow. | — | not stated | https://learn.microsoft.com/en-us/aspnet/core/fundamentals/best-practices |
| B | `ValueTask<TResult>` only when the result is often available synchronously and the method is called so often that a `Task` allocation per call matters, proven by measurement; `Task` stays the default. | Await once only; never call `AsTask` twice; never read `.Result` before completion; never mix consumption techniques; the non-generic `ValueTask` is not recommended for most cases; larger state machines. | not stated | https://learn.microsoft.com/en-us/dotnet/api/system.threading.tasks.valuetask-1 |
| B | Memory-based `ReadAsync`/`WriteAsync` overloads, and memory-based overrides when subclassing `Stream` (CA1835, CA1844). | — | not stated | https://github.com/dotnet/docs/blob/main/docs/fundamentals/code-analysis/quality-rules/performance-warnings.md |
