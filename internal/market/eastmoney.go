package market

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"sync"
	"time"

	"github.com/Zlin0509/Finace/internal/quant"
)

var fundCodePattern = regexp.MustCompile(`^\d{6}$`)

type Client struct {
	httpClient *http.Client
	mu         sync.RWMutex
	cache      map[string]cachedNAV
}

type cachedNAV struct {
	points    []quant.PricePoint
	expiresAt time.Time
}

func NewClient(timeout time.Duration) *Client {
	return &Client{httpClient: &http.Client{Timeout: timeout}, cache: make(map[string]cachedNAV)}
}

func (c *Client) FundNAV(ctx context.Context, code, start, end string) ([]quant.PricePoint, error) {
	if !fundCodePattern.MatchString(code) {
		return nil, errors.New("基金代码必须是 6 位数字")
	}
	cacheKey := code + "|" + start + "|" + end
	c.mu.RLock()
	cached, found := c.cache[cacheKey]
	c.mu.RUnlock()
	if found && time.Now().Before(cached.expiresAt) {
		return append([]quant.PricePoint(nil), cached.points...), nil
	}
	points, err := c.fundTrend(ctx, code, start, end)
	if err == nil && len(points) > 0 {
		c.remember(cacheKey, points)
		return append([]quant.PricePoint(nil), points...), nil
	}
	points, err = c.fundNAVPages(ctx, code, start, end)
	if err == nil {
		c.remember(cacheKey, points)
	}
	return points, err
}

func (c *Client) remember(key string, points []quant.PricePoint) {
	c.mu.Lock()
	c.cache[key] = cachedNAV{points: append([]quant.PricePoint(nil), points...), expiresAt: time.Now().Add(6 * time.Hour)}
	c.mu.Unlock()
}

func (c *Client) fundTrend(ctx context.Context, code, start, end string) ([]quant.PricePoint, error) {
	endpoint := "https://fund.eastmoney.com/pingzhongdata/" + code + ".js"
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, err
	}
	request.Header.Set("Referer", "http://fund.eastmoney.com/")
	request.Header.Set("User-Agent", "FundMaster-Go/0.3")
	response, err := c.httpClient.Do(request)
	if err != nil {
		return nil, fmt.Errorf("获取基金历史文件失败: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("基金历史文件返回 HTTP %d", response.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, 4<<20))
	if err != nil {
		return nil, err
	}
	marker := []byte("var Data_netWorthTrend")
	markerIndex := bytes.Index(body, marker)
	if markerIndex < 0 {
		return nil, errors.New("基金历史文件缺少净值序列")
	}
	arrayOffset := bytes.IndexByte(body[markerIndex:], '[')
	if arrayOffset < 0 {
		return nil, errors.New("基金历史净值格式无效")
	}
	var trend []struct {
		Timestamp int64   `json:"x"`
		NAV       float64 `json:"y"`
	}
	if err := json.NewDecoder(bytes.NewReader(body[markerIndex+arrayOffset:])).Decode(&trend); err != nil {
		return nil, fmt.Errorf("解析基金历史净值失败: %w", err)
	}
	china := time.FixedZone("CST", 8*60*60)
	points := make([]quant.PricePoint, 0, len(trend))
	for _, item := range trend {
		date := time.UnixMilli(item.Timestamp).In(china).Format("2006-01-02")
		if (start != "" && date < start) || (end != "" && date > end) || item.NAV <= 0 {
			continue
		}
		points = append(points, quant.PricePoint{Date: date, Price: item.NAV})
	}
	sort.Slice(points, func(i, j int) bool { return points[i].Date < points[j].Date })
	if len(points) == 0 {
		return nil, errors.New("指定区间没有可用净值")
	}
	return points, nil
}

func (c *Client) fundNAVPages(ctx context.Context, code, start, end string) ([]quant.PricePoint, error) {
	type responsePayload struct {
		Data *struct {
			List []struct {
				Date string `json:"FSRQ"`
				NAV  string `json:"DWJZ"`
			} `json:"LSJZList"`
		} `json:"Data"`
		ErrCode    int    `json:"ErrCode"`
		ErrMsg     string `json:"ErrMsg"`
		TotalCount int    `json:"TotalCount"`
	}

	const pageSize = 20
	points := make([]quant.PricePoint, 0, pageSize)
	for page := 1; ; page++ {
		values := url.Values{}
		values.Set("fundCode", code)
		values.Set("pageIndex", strconv.Itoa(page))
		values.Set("pageSize", strconv.Itoa(pageSize))
		values.Set("startDate", start)
		values.Set("endDate", end)
		endpoint := "https://api.fund.eastmoney.com/f10/lsjz?" + values.Encode()
		request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
		if err != nil {
			return nil, err
		}
		request.Header.Set("Referer", "http://fundf10.eastmoney.com/")
		request.Header.Set("User-Agent", "FundMaster-Go/0.3")
		response, err := c.httpClient.Do(request)
		if err != nil {
			return nil, fmt.Errorf("获取基金净值失败: %w", err)
		}
		var payload responsePayload
		decodeErr := json.NewDecoder(response.Body).Decode(&payload)
		response.Body.Close()
		if response.StatusCode != http.StatusOK {
			return nil, fmt.Errorf("基金数据接口返回 HTTP %d", response.StatusCode)
		}
		if decodeErr != nil {
			return nil, fmt.Errorf("解析基金净值失败: %w", decodeErr)
		}
		if payload.Data == nil {
			return nil, fmt.Errorf("基金数据为空: %s", payload.ErrMsg)
		}
		for _, item := range payload.Data.List {
			price, err := strconv.ParseFloat(item.NAV, 64)
			if err != nil || price <= 0 {
				continue
			}
			points = append(points, quant.PricePoint{Date: item.Date, Price: price})
		}
		if len(points) >= payload.TotalCount || len(payload.Data.List) < pageSize {
			break
		}
	}
	sort.Slice(points, func(i, j int) bool { return points[i].Date < points[j].Date })
	if len(points) == 0 {
		return nil, errors.New("指定区间没有可用净值")
	}
	return points, nil
}
