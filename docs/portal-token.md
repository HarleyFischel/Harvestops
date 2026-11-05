# Portal-to-app token exchange sample

`harvestops.token_exchange.PortalTokenExchange` is an isolated trust-model demonstration. It issues short-lived RS256 JWTs with `iss`, `aud`, `iat`, `nbf`, `exp`, `jti`, and `kid`, then consumes each `jti` once through a replay store. It is not an implementation of Pero Central.

The exchange should happen through a back-channel or authenticated POST, not by placing a long-lived bearer token in a URL. The receiving service must validate the explicit RS256 algorithm, issuer, audience, time claims, subject, and key identifier before creating its own short-lived session.

Key rotation: publish a new public key under a new `kid`, accept both old and new kids during the overlap window, switch issuers to the new key, then retire the old key after all short-lived tokens have expired. Store private keys in a managed secret store and keep replay state shared across replicas. The current sample intentionally has one `demo-key-1` key and an in-memory replay store; production key distribution and shared replay storage are not verified.
