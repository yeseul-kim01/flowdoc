# FlowDoc 사용법

내 Spring Boot 백엔드에 FlowDoc을 붙여 내부 호출 흐름을 보는 방법. 큰 흐름은 세 단계다:

```
① 어노테이션 달기  →  ② 스캔해서 flowdoc.json 생성  →  ③ 뷰어로 보기
```

핵심 원칙: **파서가 읽을 수 있는 건 자동으로 가져온다.** 표준 어노테이션(`@Transactional`,
`@PostMapping`, `@Async`, `@Repository` …)과 호출 관계·파라미터·Javadoc은 그대로 읽으므로,
사람이 다는 건 "정적으로 알 수 없는 의도"뿐이다. 사실상 `@FlowEntry` 하나로 시작할 수 있다.

전체 예제는 [examples/coupon-rush](../examples/coupon-rush/)를 그대로 따라 하면 된다.

---

## 0. 사전 요구사항

- JDK 21+
- Gradle (래퍼 제공)

---

## 1. 의존성 추가

FlowDoc 모듈은 아직 Maven Central에 배포 전이라, 같은 저장소의 구현을 **composite build**로 끌어 쓴다
(coupon-rush 예제와 동일). 별도 프로젝트라면 `includeBuild`로 `flowdoc-java`를 가리키면 된다.

```groovy
// settings.gradle
includeBuild('/path/to/FlowDoc/flowdoc-java')

// build.gradle
dependencies {
    // 코드가 직접 import 하는 선언 어노테이션
    implementation 'io.flowdoc:flowdoc-annotations:0.1.0-SNAPSHOT'

    // (선택) 실행 중인 앱이 /flowdoc 에서 뷰어 + 스펙을 라이브로 서빙
    implementation 'io.flowdoc:flowdoc-spring-boot-starter:0.1.0-SNAPSHOT'
}
```

> 스타터 없이 스펙만 뽑아 standalone 뷰어로 봐도 된다(4-B). 그 경우 `flowdoc-annotations`만 있으면 되고,
> 어노테이션을 전혀 안 써도(표준 어노테이션만으로도) 흐름은 그려진다 — 단, `@FlowEntry`가 없으면 진입점이 없어
> "시퀀스 없음"으로 표시된다.

---

## 2. 어노테이션 달기

### FlowDoc이 정의하는 명시 어노테이션 (필요한 것만)

| 어노테이션 | 용도 | 비고 |
|---|---|---|
| `@FlowEntry("tag")` | **시퀀스 진입점 + 이름.** 화면 한 장의 시작점 | 사실상 유일한 필수. 컨트롤러뿐 아니라 리스너·스케줄러에도 가능 |
| `@Guarded(resource, permits, type)` | 동시성 가드의 *의미* 선언 (어떤 자원을 몇 permit로) | `type`은 `SEMAPHORE`(기본)/`LOCK` |
| `@FlowExternal` | 외부 시스템 경계 — 노드로 그리되 내부로 안 파고듦 | |
| `@FlowIgnore` | 이 메서드를 그래프에서 제외 | 노이즈 제거 |
| `@FlowDoc(summary, params=@Param(name, desc))` | 구조적 설명 (Swagger `@Operation(description=)` 대응) | 안 달면 **Javadoc**을 자동으로 읽음 |

### FlowDoc이 그냥 읽기만 하는 표준 어노테이션

`@Transactional`(tx 레일), `@PostMapping`/`@GetMapping`(라우트 배지·진입점 후보), `@Async`(레일 밖
비동기), `@Repository`/Spring Data 저장소(데이터 경계 노드), `@Service`/`@RestController`(계층) 등은
**다시 선언하지 않는다.** 코드에 이미 있으면 자동 반영된다.

### 예시

```java
@RestController
class CouponController {
    @FlowDoc(summary = "선착순 쿠폰 발급 진입점.",
             params = @Param(name = "campaignId", desc = "캠페인 ID"))
    @PostMapping("/{campaignId}/coupons")
    @FlowEntry("issue-coupon")                // ← 이 흐름의 시작점
    IssueResult issue(@PathVariable Long campaignId, @RequestBody IssueRequest req) { … }
}

@Service
class CouponService {
    /** 발급을 하나의 트랜잭션으로 처리한다. */   // ← Javadoc 이 설명으로 자동 추출됨
    @Transactional
    IssueResult issue(Long campaignId, Long userId) { … }

    @Guarded(resource = "coupon-stock", permits = 1)
    Campaign reserveStock(Long campaignId) { … }
}
```

---

## 3. 스펙 생성 (스캔)

스캐너는 **소스만 파싱**한다(컴파일·실행 불필요, 의존성 jar도 클래스패스에 없어도 됨).

```bash
cd flowdoc-java
./gradlew :flowdoc-scanner:run \
  --args="/내앱/src/main/java  /출력/flowdoc.json"
```

라이브 `/flowdoc`로 보려면 출력 경로를 앱의 **리소스 루트**로 잡는다(스타터가 `classpath:flowdoc.json`을 서빙):

```bash
./gradlew :flowdoc-scanner:run \
  --args="/내앱/src/main/java  /내앱/src/main/resources/flowdoc.json"
```

> 스펙은 **빌드 시점에 prebuilt** 된다. 실행 중인 jar 안엔 소스가 없어 런타임 자가 스캔은 불가하다
> (런타임 수집은 로드맵 v0.3의 AOP 에이전트). 코드를 바꾸면 다시 스캔 → 앱 재시작.

---

## 4. 보기

### A) 라이브 `/flowdoc` (스타터)

```bash
./gradlew bootRun
# → http://localhost:8080/flowdoc
```

| 요청 | 응답 |
|---|---|
| `GET /flowdoc` | `/flowdoc/`로 리다이렉트 |
| `GET /flowdoc/` | HTML 뷰어 |
| `GET /flowdoc/flowdoc.json` | 스펙 (뷰어가 fetch) |

### B) standalone 뷰어 (앱 없이)

```bash
cd ui
cp /출력/flowdoc.json ./flowdoc.json     # 같은 폴더에 두면 자동 로드
python3 -m http.server 8080              # → http://localhost:8080
```

`index.html`을 직접 열면 드롭존이 뜨고 `flowdoc.json`을 끌어다 놓으면 된다.
`?spec=/경로/flowdoc.json`로 임의 스펙을 가리킬 수도 있다.

### 화면에서 보이는 것

진입점에서 시작하는 호출 트리. `@Transactional`은 amber tx 레일, `@Guarded`는 red 배지,
`@Async`는 레일 밖(teal), `@Repository`/외부는 경계 배지. 행을 누르면 파라미터·리턴·어노테이션·위치
(`auto`)와 설명(`declared`)이 펼쳐진다.

---

## 5. 설정 (`application.yml`)

스타터는 다음 프로퍼티를 받는다(모두 선택):

```yaml
flowdoc:
  enabled: true               # /flowdoc 엔드포인트 등록 여부 (기본 true)
  path: /flowdoc              # 뷰어 base 경로 (기본 /flowdoc)
  spec-location: classpath:flowdoc.json   # 스펙 위치 (Spring 리소스 표기 가능)
```

---

## 6. 동작 원리 & 한계

- **소스 파싱**(JavaParser + SymbolSolver). 내부 호출은 해석해 간선으로, `@Repository`/Spring Data·
  `@FlowExternal` 호출은 경계 노드로 그린다. 그 외 정말 알 수 없는 대상은 **추측하지 않고 버린다**.
- 풀 해석이 실패해도(예: record 접근자 같은 인자) 수신자 타입 + 메서드명으로 폴백해 내부 호출을 복구한다.
- **현재 한계**(로드맵 v0.2 진행 중): 인터페이스 다구현은 `@FlowResolves` 전이라 동명 메서드가 유일할 때만
  연결 / getter 같은 trivial accessor가 노드로 보임 / 클래스 레벨 `@RequestMapping` 프리픽스 미합성.
  → 인터페이스 의존성은 가능하면 **구체 타입으로 주입**하면 간선이 잘 잡힌다.

---

## 7. 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| `GET /flowdoc/flowdoc.json` → 404 | 스펙이 classpath에 없음. 3절대로 `src/main/resources/flowdoc.json`에 생성 |
| "시퀀스 없음" / 흐름이 안 그려짐 | 진입점에 `@FlowEntry`가 없음. 컨트롤러/리스너 메서드에 추가 |
| 컨트롤러만 뜨고 하위가 안 붙음 | 그 호출이 외부/미해석. 의존성을 구체 타입으로 주입했는지 확인 |
| 간선이 기대보다 적음 | repository 상속 메서드·외부 호출은 경계 노드로만 표시(내부로 안 파고듦) |
| `/flowdoc`가 아예 없음 | 스타터 의존성 누락 또는 `flowdoc.enabled=false` |
