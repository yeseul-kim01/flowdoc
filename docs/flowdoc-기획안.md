# FlowDoc — 기획안

> 백엔드 내부 호출 흐름을 위한 Swagger.
> 외부 API 계약이 아니라, 요청 하나가 내부에서 *어떤 서비스의 어떤 함수를 거쳐 나가는지* 를 자동으로 문서화·도식화한다.

문서 버전: 0.1 (초안) · 대상: Java / Spring Boot 우선, Python 확장 예정
개발 기준: SpeakNote v0.1 백엔드 호환, Spring Boot 3.5.9 · Java 21

---

## 1. 한 줄 정의

FlowDoc는 백엔드 소스를 분석해 **함수 호출 흐름, 트랜잭션 경계, 동시성 가드, 비동기 후처리**를 Swagger UI 같은 인터랙티브 화면으로 그려주는 라이브러리다. 코드에서 자동으로 뽑을 수 있는 것은 자동으로 뽑고, 정적으로 알 수 없는 의도·의미만 개발자가 어노테이션으로 명시한다.

---

## 2. 문제 정의와 동기

지금 백엔드 개발자가 쓸 수 있는 도구는 두 진영으로 나뉜다. 한쪽 끝에는 Swagger/OpenAPI가 있다. 외부에서 본 API 계약, 즉 어떤 엔드포인트가 어떤 입출력을 갖는지를 잘 보여주지만 그 요청이 들어온 *뒤* 내부에서 무슨 일이 일어나는지는 전혀 다루지 않는다. 반대쪽 끝에는 분산 트레이싱(Jaeger, Zipkin, OpenTelemetry)이 있다. 실제 실행 경로를 보여주지만 운영 관측용이고, 개발자가 의도를 적어 넣는 *문서*는 아니며, 코드를 읽는 단계에서 곧장 참조하기엔 무겁다.

그 사이가 비어 있다. "이 요청을 처리하려고 어느 서비스 어떤 함수를 거치지? 그 중 어디가 한 트랜잭션으로 묶이지? 이 재고 차감은 동시성 보호가 되고 있나? 알림은 커밋 전에 나가나 후에 나가나?" 이런 질문은 보통 코드를 직접 따라 읽거나 선임에게 물어서 답한다. FlowDoc는 이 질문에 대한 답을 코드에서 자동으로 만들어, 협업과 온보딩과 리뷰의 비용을 낮추는 것을 목표로 한다.

---

## 3. 목표와 비목표

**목표**

내부 호출 흐름의 구조를 자동으로 추출해 사람이 읽기 좋은 형태로 보여준다. 트랜잭션 경계, 동시성 가드(세마포어·락), 비동기 경계를 일급 개념으로 표현한다. Swagger처럼 개발자가 적은 설명·입출력 의미가 자동 추출 정보와 함께 뜬다. 진입점 태그 하나를 기준으로 "사용자 시퀀스 요청 하나의 경로"를 그린다. Java/Spring Boot에서 먼저 동작하되, 같은 스펙을 공유해 Python으로 확장할 수 있는 구조를 처음부터 갖춘다.

**비목표 (적어도 v1에서는)**

런타임 성능 프로파일링이나 APM 대체는 목표가 아니다. 정적 분석이 추론할 수 없는 것을 억지로 추측하지 않는다 — 모르면 "모호함"으로 표시하거나 명시를 요구한다. 전체 코드베이스를 한 장에 그리는 것을 목표로 하지 않는다. 흐름은 항상 진입점 태그를 기준으로 범위가 잡힌다.

---

## 4. 핵심 개념과 용어

**노드(Node)** — 흐름에 등장하는 함수 하나. 이름, 위치, 파라미터, 리턴, 어노테이션, 설명을 가진다.

**간선(Edge)** — "A가 B를 호출한다"는 호출 관계. 동기/비동기/이벤트 종류와 호출 위치(파일:라인)를 가진다.

**시퀀스(Sequence)** — `@FlowEntry` 태그가 붙은 진입점에서 시작하는 하나의 흐름. 화면 한 장의 단위.

**가드(Guard)** — 세마포어·락처럼 동시성을 보호하는 표시. 어떤 논리적 자원을 몇 permit로 보호하는지.

**트랜잭션 경계(Transaction boundary)** — `@Transactional` 메서드가 여는 묶음. 그 안에서 실행되는 호출들이 한 단위로 커밋/롤백된다.

**트레이스(Trace)** — (런타임 단계) 실제로 한 번 실행된 경로의 순서 있는 기록. 구조 그래프 위에 덧칠된다.

**auto / declared** — 노드의 정보는 두 출처로 나뉜다. `auto`는 파서가 코드 구조에서 자동으로 뽑은 것, `declared`는 개발자가 어노테이션으로 명시한 것.

---

## 5. 자동 인식 vs 명시 선언 (핵심 원칙)

FlowDoc의 전체 설계는 이 한 줄에 걸려 있다: **파서가 읽을 수 있는 것은 절대 사람에게 시키지 않고, 정적으로 알 수 없는 의도·정체·의미만 명시를 요구한다.** 이 선을 지키지 못하면 FlowDoc는 Swagger가 아니라 수동 다이어그램 그리기 도구로 전락한다.

| 구분 | 항목 | 출처 |
|---|---|---|
| **자동 (auto)** | 함수 이름, 소속 클래스, 위치(파일:라인) | 정적 |
| | 파라미터 이름·타입, 리턴 타입 | 정적 |
| | 코드에 이미 달린 표준 어노테이션 (`@Transactional`, `@Async`, `@PostMapping`, `@Repository` 등) | 정적 |
| | 본문에서 호출하는 함수들 (호출 간선) | 정적 |
| | Javadoc → 설명 텍스트 | 정적 |
| **명시 (declared)** | 어떤 메서드가 시퀀스 진입점인가 (`@FlowEntry`) | 어노테이션 |
| | `semaphore.acquire()`가 어떤 논리적 자원을 몇 permit로 보호하는가 (`@Guarded`) | 어노테이션 |
| | 인터페이스 호출이 구현 다수일 때 어디로 가는가 (`@FlowResolves`) | 어노테이션 / 런타임 |
| | 이벤트 발행이 어느 핸들러로 이어지는가 (`@FlowLink`) | 어노테이션 / 타입 매칭 |
| | 외부 시스템 경계 (`@FlowExternal`), 그래프에서 제외 (`@FlowIgnore`) | 어노테이션 |
| **런타임으로만 확정** | 실제 분기 선택, 반복 횟수, 재시도 | 트레이스 |
| | 트랜잭션 전파의 실제 동작(신규 vs 합류), 실제 커밋/롤백 | 트레이스 |
| | 세마포어 획득·해제의 실제 순서, async 실제 스레드 | 트레이스 |

호출이 *존재한다*는 사실은 정적 파서가 본다. 그 호출이 *무슨 의미인지*만 사람이 적는다. 그리고 나중에 런타임 추적이 붙으면 명시한 의도를 실제 실행으로 사후 검증·보강한다.

---

## 6. 어노테이션 명세

어노테이션은 두 부류다. FlowDoc이 *정의해서 개발자가 명시하는* 것(6.1)과, 이미 코드에 달려 있어 FlowDoc이 *읽기만 하는* 표준 어노테이션(6.2).

### 6.1 명시 어노테이션 (FlowDoc 정의)

작고 원칙 있는 세트로 유지한다. 각 어노테이션은 "정적으로 추론 불가능한 의도/정체/의미"를 메우는 단 하나의 이유로만 존재한다.

```java
// 시퀀스 진입점 표시 + 이름 부여. 화면 한 장의 시작점.
@FlowEntry("place-order")

// 동시성 가드의 의미를 선언. 호출 자체는 파서가 봐도 의미는 모른다.
@Guarded(resource = "inventory", type = SEMAPHORE, permits = 1)

// 구현이 여러 개인 인터페이스 호출의 실제 대상을 힌트로 준다.
@FlowResolves(InventoryServiceImpl.class)

// 이벤트 발행 → 핸들러 연결을 명시 (타입 매칭으로 자동 추론 못 할 때).
@FlowLink(event = OrderPlaced.class, to = "OrderPlacedHandler#on")

// 외부 시스템 경계. 노드로는 그리되 내부로 더 파고들지 않는다.
@FlowExternal

// 노이즈 제거. 이 메서드/간선을 그래프에서 뺀다.
@FlowIgnore

// (선택) Javadoc 대신 구조적 설명을 주고 싶을 때.
@FlowDoc(summary = "...", params = { @Param(name = "cmd", desc = "...") })
```

### 6.2 인식 어노테이션 레지스트리 (FlowDoc이 읽기만 하는 표준)

핵심은 어노테이션을 단순 목록으로 모으는 게 아니라 **어노테이션 → 의미 역할(semantic role) → 렌더링** 으로 매핑하는 것이다. 가치는 목록이 아니라 매핑에 있다. `@Transactional`은 "트랜잭션 경계", `@Cacheable`은 "단락 가능 지점", `@KafkaListener`는 "진입점" 식으로 역할을 부여해야 UI가 의미 있게 그린다. 아래는 내장 기본값이다.

| 의미 역할 | 대표 어노테이션 | FlowDoc 처리 |
|---|---|---|
| **진입점** | `@GetMapping`·`@PostMapping`·`@RequestMapping` 등, `@KafkaListener`, `@RabbitListener`, `@JmsListener`, `@EventListener`, `@Scheduled`, `@MessageMapping` | `@FlowEntry` 후보로 자동 제안 + 라우트/트리거 배지. 흐름은 컨트롤러에서만 시작하지 않는다 |
| **트랜잭션** | `@Transactional`, `@TransactionalEventListener` | tx 레일, propagation 표시. 이벤트 리스너는 커밋 *단계*(AFTER_COMMIT 등)에 연결 |
| **동시성·복원력** | `@Async`, `@Lock`(JPA), `@Retryable`/`@Recover`(Spring Retry), `@CircuitBreaker`·`@RateLimiter`·`@Bulkhead`·`@TimeLimiter`(Resilience4j는 `@Retry`), `@SchedulerLock`(ShedLock) | 가드/경계 마커, async 분리, 재시도·폴백 간선 |
| **데이터 경계** | `@Repository`, `@Query`, `@Modifying`, `@Lock` | 저장소 배지, 읽기/쓰기 구분, 락 표시 |
| **캐시** | `@Cacheable`, `@CachePut`, `@CacheEvict`, `@Caching` | 본문을 건너뛸 수 있는 단락 지점으로 표시 |
| **보안 게이트** | `@PreAuthorize`, `@PostAuthorize`, `@Secured`, `@RolesAllowed` | 흐름 진입 게이트 마커 |
| **입력 바인딩·검증** | `@RequestBody`, `@RequestParam`, `@PathVariable`, `@Valid`, `@Validated`, `@NotNull`·`@Size` 등 | 파라미터 소스·제약을 Swagger식으로 표시 |
| **역할(스테레오타입)** | `@Service`, `@Component`, `@Controller`, `@RestController`, `@RestControllerAdvice` | 계층 배지, 에러 처리 경계 |
| **관측** | `@Observed`, `@Timed`, `@NewSpan`, `@SpanTag` (Micrometer) | 이미 박혀 있는 트레이스 포인트를 재사용 |

**놓치기 쉬운 고가치 항목.** `@TransactionalEventListener`는 이벤트가 트랜잭션 커밋 단계에 묶이므로 tx 경계와 반드시 연결한다. `@Modifying`은 그 저장소 호출이 읽기가 아니라 *쓰기*라는 신호다. JPA `@Lock`은 사실상 세마포어와 같은 동시성 가드라 자동으로 가드 개념에 포함된다. `@Retryable`/`@CircuitBreaker`의 폴백 메서드는 *대체 간선*을 만든다.

**무시할 어노테이션.** DI·설정·직렬화·보일러플레이트(`@Autowired`, `@Value`, `@Bean`, `@Configuration`, `@ConfigurationProperties`, Jackson `@Json*`, Lombok `@Getter`/`@Slf4j`/`@RequiredArgsConstructor` 등)는 흐름 렌더링에 영향이 없으니 스캐너가 건너뛴다. 구조 파악에만 부수적으로 참고한다.

**확장성은 필수.** 위 표의 절반 이상이 서드파티(Resilience4j, Spring Retry, Kafka, ShedLock)이고, 회사마다 커스텀 어노테이션(`@DistributedLock` 같은)을 쓴다. 따라서 기본값은 내장하되, 설정으로 임의의 FQN을 역할에 매핑할 수 있게 SPI나 설정 파일을 열어둔다. 이게 없으면 어떤 코드베이스에서는 화면 절반이 비어버린다.

```yaml
# 예시: 커스텀/서드파티 어노테이션을 역할에 매핑
flowdoc:
  annotations:
    transaction: [com.mycorp.tx.UnitOfWork]
    guard:       [com.mycorp.lock.DistributedLock]
    entry:       [com.mycorp.messaging.PubSubListener]
    ignore:      [com.mycorp.audit.Audited]
```

---

## 7. 아키텍처

스펙 우선(spec-first) 설계다. 가운데에 언어 중립 JSON 스펙을 두고, 그 스펙을 *만드는* 수집기와 *읽는* UI를 분리한다. OpenAPI 스펙과 Swagger UI의 관계와 똑같다.

```
[정적 스캐너] ─┐
[런타임 에이전트] ─┼─→ [공유 스펙 (JSON)] ─→ [FlowDoc UI (HTML)]
[Python 스캐너(추후)] ─┘        │                  구조 뷰 + 트레이스 뷰
                                 단일 진실 원천
```

**정적 스캐너 (Java)** — JavaParser + JavaSymbolSolver로 소스를 파싱한다. 클래스/메서드를 노드로, 본문의 호출식을 간선으로 만들고, 파라미터·리턴·표준 어노테이션·Javadoc을 `auto`로, FlowDoc 어노테이션을 `declared`로 채운다. 진입점(`@FlowEntry`)에서 시작해 도달 가능한 노드만 따라가며 시퀀스를 구성한다. 빌드 타임에 동작하므로 런타임 부하가 0이다.

**런타임 에이전트 (Java, 후속 단계)** — Spring AOP `@Around`로 빈 메서드의 enter/exit를 기록하고, `TransactionSynchronization`으로 트랜잭션 생명주기(begin/commit/rollback, propagation)를 잡는다. 같은 노드 ID를 참조하는 트레이스를 스펙의 `traces`에 추가한다. 구조 그래프는 그대로 두고 그 위에 실제 순서를 덧칠한다.

**공유 스펙 (JSON)** — 모든 것의 단일 진실 원천. 9절 참고.

**FlowDoc UI (HTML)** — 스펙을 받아 그리는 단일 페이지. 구조 뷰(전체 호출 트리 + 트랜잭션 레일 + 가드 표시)와 트레이스 뷰(실제 실행 순서 재생)를 제공한다. 노드를 누르면 Swagger처럼 `auto`/`doc` 정보가 펼쳐진다. 이미 프로토타입(flowdoc-example.html)으로 모양을 확정했다.

---

## 8. 공유 스펙 (JSON 스키마)

노드마다 `auto`/`declared`/`markers`를 나눠 담고, 간선은 해석 신뢰도(`resolution`)를 갖고, 시퀀스는 진입 태그로 묶이며, 트레이스는 선택적 런타임 오버레이다.

```json
{
  "flowdoc": "0.1",
  "source": { "language": "java", "framework": "spring-boot", "collector": "static" },

  "nodes": [
    {
      "id": "com.shop.order.OrderService#createOrder(CreateOrderCommand)",
      "simpleName": "createOrder",
      "owner": "OrderService",
      "kind": "method",
      "location": { "file": "OrderService.java", "line": 88, "module": "order" },
      "auto": {
        "params": [{ "name": "cmd", "type": "CreateOrderCommand" }],
        "returns": { "type": "Order" },
        "annotations": [
          { "name": "Transactional", "attributes": { "propagation": "REQUIRED" } }
        ]
      },
      "declared": {
        "description": "재고 예약 → 결제 → 저장 → 이벤트 발행을 하나의 트랜잭션으로 묶는다. 어느 단계든 실패하면 전체 롤백.",
        "paramDocs": { "cmd": "검증을 통과한 주문 커맨드" }
      },
      "markers": {
        "transaction": { "boundary": "open", "propagation": "REQUIRED" }
      }
    },
    {
      "id": "com.shop.order.OrderRepository#save()",
      "simpleName": "save",
      "owner": "OrderRepository",
      "kind": "external",
      "location": { "file": "OrderService.java", "line": 95 },
      "auto": { "params": [], "annotations": [{ "name": "Repository" }] }
    },
    {
      "id": "com.shop.notify.NotificationService#notifyPlaced(Order)",
      "simpleName": "notifyPlaced",
      "owner": "NotificationService",
      "kind": "method",
      "location": { "file": "NotificationService.java", "line": 20 },
      "auto": {
        "params": [{ "name": "order", "type": "Order" }],
        "annotations": [{ "name": "Async" }]
      }
    }
  ],

  "edges": [
    {
      "from": "com.shop.order.OrderController#placeOrder(PlaceOrderRequest)",
      "to": "com.shop.order.OrderService#createOrder(CreateOrderCommand)",
      "callType": "sync",
      "site": { "file": "OrderController.java", "line": 50 },
      "condition": null,
      "resolution": "concrete"
    },
    {
      "from": "com.shop.order.OrderService#createOrder(CreateOrderCommand)",
      "to": "com.shop.order.OrderRepository#save()",
      "callType": "sync",
      "site": { "file": "OrderService.java", "line": 95 },
      "condition": null,
      "resolution": "concrete"
    },
    {
      "from": "com.shop.order.OrderService#createOrder(CreateOrderCommand)",
      "to": "com.shop.notify.NotificationService#notifyPlaced(Order)",
      "callType": "async",
      "site": { "file": "OrderService.java", "line": 98 },
      "condition": null,
      "resolution": "concrete"
    }
  ],

  "guards": [
    {
      "nodeId": "com.shop.inventory.InventoryService#reserve(List)",
      "type": "semaphore", "resource": "inventory", "permits": 1,
      "source": "declared"
    }
  ],

  "sequences": [
    {
      "tag": "place-order",
      "title": "주문 생성 시퀀스",
      "entry": "com.shop.order.OrderController#placeOrder(PlaceOrderRequest)",
      "description": "요청이 진입점에서 시작해 어떤 함수를 거쳐 나가는지.",
      "transactions": [
        {
          "owner": "com.shop.order.OrderService#createOrder(CreateOrderCommand)",
          "covers": ["...reserve(List)", "...charge(Order,Card)", "...save(Order)", "...publish(OrderPlaced)"]
        }
      ]
    }
  ],

  "traces": [
    {
      "traceId": "abc123",
      "sequenceTag": "place-order",
      "spans": [
        { "id": "s0", "nodeId": "...placeOrder(...)", "parent": null, "tEnter": 0, "tExit": 142, "thread": "http-1" },
        { "id": "s1", "nodeId": "...createOrder(...)", "parent": "s0", "tEnter": 2, "tExit": 138,
          "tx": { "id": "tx-1", "event": "begin->commit" } },
        { "id": "s2", "nodeId": "...reserve(...)", "parent": "s1", "tEnter": 4, "tExit": 30,
          "guard": { "resource": "inventory", "acquiredAt": 4, "releasedAt": 30 } }
      ]
    }
  ]
}
```

`edges[].resolution` 값: `concrete`(구체 타입 호출), `single-impl`(인터페이스인데 구현 1개라 자동 매핑), `ambiguous`(구현 다수, 명시 필요), `runtime-confirmed`(트레이스가 확정). UI는 이 신뢰도를 시각적으로 구분한다.

`edges[].callType` 값: `sync`(직접 호출), `async`(`@Async` 등 커밋 후 별도 스레드 — tx 레일 밖에 배치), `event`(이벤트 디커플링, 점선). `nodes[].kind`는 보통 `method`지만, `@Repository`·Spring Data 저장소나 `@FlowExternal` 대상처럼 소스에 정의가 없는 경계는 `kind: "external"` 노드로 그린다(상속 시그니처를 날조하지 않고 경계만 표시, 내부로 더 파고들지 않음). 위 예시의 `OrderRepository#save()`가 이 경우다.

---

## 9. 트랜잭션·동시성·비동기 모델링

**트랜잭션 경계** — `@Transactional` 메서드는 노드 `markers.transaction.boundary = "open"`을 갖고, 시퀀스의 `transactions[].covers`에 그 트랜잭션 안에서 실행되는 호출들이 나열된다. UI는 이 묶음을 왼쪽 amber 레일(`tx begin … commit`)로 감싼다. propagation은 `auto`에서 읽되, 신규 트랜잭션인지 합류인지의 *실제* 동작은 런타임 트레이스가 확정한다.

**동시성 가드** — `@Guarded`로 선언된 노드는 `guards[]`에 들어간다. 정적 단계에서는 "이 호출은 inventory 세마포어(permit 1)로 보호됨"까지 표현하고, 런타임 단계에서 실제 획득·해제 시각(`acquiredAt`/`releasedAt`)을 트레이스에 채워 임계 구역의 실제 지속 시간을 보여준다.

**비동기 경계** — `@Async` 노드는 트랜잭션 레일 *밖*에 배치된다. 의미가 "커밋 후 별도 스레드"이기 때문이다. 여기서 실패해도 메인 트랜잭션이 롤백되지 않는다는 점을 UI가 명시한다.

**이벤트** — 발행 노드와 핸들러 노드를 `@FlowLink` 또는 이벤트 타입 매칭으로 연결한다. 동기 호출이 아니라 디커플링된 연결이므로 간선 `callType = "event"`로 구분해 점선 등으로 표현한다.

---

## 10. UI/UX 설계

프로토타입에서 확정한 방향을 기준으로 한다.

**구조 뷰** — 진입점에서 시작하는 들여쓰기 호출 트리. 각 행은 모노스페이스 시그니처(클래스.메서드(파라미터): 리턴)와 오른쪽 배지(어노테이션). 트랜잭션 묶음은 amber 레일, 세마포어 가드는 red 배지, async는 teal 배지, 외부 호출은 blue 배지. 행을 누르면 상세 패널이 펼쳐지고 `auto` 칩(파라미터·리턴·어노테이션·위치)과 `doc` 칩(설명)이 구분되어 표시된다.

**트레이스 뷰 (런타임 단계)** — 같은 트리 위에 실제 실행을 재생. 실제로 탄 간선만 강조하고, 안 탄 분기는 흐리게. 트랜잭션 begin→commit 구간, 세마포어 점유 구간, async가 갈라지는 지점을 타임라인으로 보여준다.

**시퀀스 목록** — 좌측에 `@FlowEntry` 태그 목록(여러 시퀀스). 프로토타입은 하나만 깔았지만 실제로는 사이드바로 전환 가능하게.

**탐색** — 한 함수가 여러 시퀀스에 등장할 때 역참조("이 함수가 쓰이는 시퀀스들") 제공. 깊은 트리는 깊이 제한 + 펼치기, 재귀/순환은 `↻` 마커로 표시하고 무한 전개를 막는다.

---

## 11. 기술적 난제와 해결 전략

**인터페이스 → 구현 해석** — Spring DI/프록시 때문에 정적으로 호출 대상을 단정하기 어렵다. 전략: 구현이 1개면 자동 매핑(`single-impl`), 다수면 `ambiguous`로 표시하고 `@FlowResolves` 힌트를 받거나 런타임 트레이스로 확정. 절대 추측해서 단정하지 않는다.

**조건 분기·반복·재시도** — 정적으로는 *가능한* 경로를 모두 그리되 간선에 `condition` 메타를 달아 UI가 "조건부"로 구분. 실제로 어느 분기를 탔는지는 런타임 트레이스가 확정.

**재귀·순환** — 그래프 사이클을 탐지해 `↻` 마커로 표현하고, 트리 전개는 깊이 제한으로 보호.

**대규모 코드베이스 / 멀티모듈** — 전체를 그리지 않는다. 항상 진입점 태그 기준으로 도달 범위만 그래프화. 모듈 정보를 노드에 담아 모듈 경계를 시각화.

**파라미터 이름 보존** — 자바 바이트코드는 기본적으로 파라미터 이름을 버린다. 소스 기반(JavaParser)이면 문제없지만, 컴파일 결과만 있을 땐 `-parameters` 컴파일 플래그나 디버그 정보가 필요. v1은 소스 분석을 기본으로.

**런타임 오버헤드** — 에이전트는 옵트인이고, 특정 시퀀스 태그만 샘플링하도록 범위를 좁힌다. 운영 상시 가동이 아니라 개발/스테이징 또는 온디맨드 캡처를 기본 가정.

---

## 12. 다국어 확장 (Python)

언어 중립 스펙 덕분에 Python 지원은 "스펙을 뱉는 새 수집기"만 만들면 된다. UI는 그대로 재사용. Python 정적 수집기는 `ast` 모듈로 함수·호출을 추출하고, 데코레이터(`@flow_entry`, `@guarded` 등)로 명시 정보를 받는다. 런타임 수집기는 `sys.setprofile`이나 데코레이터 래핑으로 트레이스를 만든다. 어노테이션 철학과 auto/declared 경계는 언어와 무관하게 동일하게 유지한다.

---

## 13. 패키징과 통합

**빌드 플러그인** — Gradle/Maven 플러그인이 빌드 타임에 정적 스캐너를 돌려 `flowdoc.json`과 이를 로드하는 단일 HTML을 산출. CI에 붙이면 PR마다 흐름 문서가 갱신된다.

**런타임 스타터 (선택)** — `flowdoc-spring-boot-starter`를 의존성에 추가하면 `/flowdoc` 엔드포인트에서 라이브로 보여준다. springdoc-openapi가 `/swagger-ui`를 띄우는 방식과 동일. 런타임 에이전트가 붙으면 여기서 트레이스 뷰까지.

**산출물** — 정적 JSON 스펙(이식·버전관리 가능), 단일 HTML 뷰어, (선택) 라이브 엔드포인트.

---

## 14. 로드맵

**v0.1 — 스펙 + 정적 코어** ✅
JSON 스펙 스키마 확정. JavaParser 기반 스캐너로 노드/간선/`auto` 필드 + `@FlowEntry`·`@Transactional`·`@Guarded` 읽기. FlowDoc UI 구조 뷰(프로토타입을 실제 스펙 소비로 연결).

**v0.2 — 정적 완성도** 🔄 _(진행 중)_
- ✅ Javadoc → 설명 + `@FlowDoc(summary, params)` 명시 설명
- ✅ `@Repository`/Spring Data·`@FlowExternal` 호출을 외부 경계 노드로 표현, async 간선(`@Async`), 간선 중복 제거
- ✅ 수신자 타입 폴백 해석(인자 해석 실패 시에도 내부 호출 복구)
- ✅ 라이브 `/flowdoc` 스타터(`flowdoc-spring-boot-starter`) — 원래 v1.0 계획이었으나 조기 구현
- ⬜ 인터페이스 단일 구현 완전 해석 + `@FlowResolves`, `@FlowIgnore`, Gradle/Maven 빌드 플러그인, getter 등 노이즈 필터링

**v0.3 — 런타임 오버레이**
Spring AOP 에이전트 + `TransactionSynchronization`으로 트레이스 수집. UI 트레이스 뷰. 명시한 의도의 사후 검증.

**v0.4 — 연결성**
이벤트 발행↔핸들러 연결, 모호성 해소, 멀티모듈 경계.

**v1.0 — 안정화 + 확장**
문서·패키징 정리. Python 수집기(별도 트랙)로 같은 스펙 산출. (라이브 엔드포인트는 v0.2에서 선행.)

---

## 15. 성공 지표 / 오픈 퀘스천

**성공의 모습** — 새 팀원이 코드를 직접 따라 읽지 않고도 한 시퀀스의 흐름·트랜잭션·동시성을 파악할 수 있다. 흐름 문서가 빌드마다 자동 갱신되어 항상 코드와 일치한다. 어노테이션 부담이 작아서 개발자가 실제로 단다.

**아직 열린 질문** — 어노테이션 세트를 어디까지 최소화할 수 있나(특히 이벤트 연결). 트레이스 뷰에서 여러 트레이스를 어떻게 집계해 보여줄까(평균 경로 vs 단일 경로). 정적 그래프와 런타임 트레이스가 어긋날 때(코드가 바뀐 경우) 어떻게 표시할까. 멀티스레드/리액티브(WebFlux) 흐름을 어떻게 모델링할까.
