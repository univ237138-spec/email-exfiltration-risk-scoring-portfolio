# 데이터

이 저장소에는 원본 데이터, 정답 파일, 사용자·일 단위 파생 데이터가 들어 있지 않습니다.
CERT r4.2 이용 약관은 데이터나 그 일부를 인터넷에 게시하는 것을 금지합니다. 보고서처럼 성능을 설명하는 데 필요한 최소한의 파생물만 허용합니다. 그래서 요약 수치와 그림만 포함했습니다.

## 받는 방법

1. [CERT Insider Threat Test Dataset (KiltHub, CMU SEI)](https://kilthub.cmu.edu/articles/dataset/Insider_Threat_Test_Dataset/12841247)에서 `r4.2.tar.bz2`와 `answers.tar.bz2`를 받습니다.
2. 작업 당시 폴더 구조에 맞춰 풉니다.

```
inputs/
├── events/     email.csv, logon.csv, device.csv, file.csv, http.csv, psychometric.csv
└── LDAP/       2009-12.csv ~ 2011-05.csv
labels/
└── answers/    insiders.csv, r4.2-1/, r4.2-2/, r4.2-3/
```

3. 파이프라인을 순서대로 실행합니다(저장소 루트의 README 참고). 생성물은 `outputs/`에 저장됩니다.

정답(`labels/`)은 **평가 스크립트에서만** 읽습니다. 점수와 경계를 만드는 코드(`src/`)는 정답을 읽지 않습니다.

## 규모 (r4.2)

| 파일 | 행 수 |
|---|---:|
| email.csv | 1,314,400 |
| logon.csv | 854,859 |
| http.csv | 1,422,900 |
| file.csv | 445,581 |
| device.csv | 405,380 |
| LDAP (월별 18개) | 16,743 |
| psychometric.csv | 1,000 |
