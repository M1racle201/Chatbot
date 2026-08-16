#include <iostream>
#include <vector>
#include <algorithm>   // std::swap
#include <cstdlib>     // rand(), srand()
#include <ctime>       // time()

using namespace std;

/**
 * 快速排序 - 三数取中法选取基准
 * 优化点：
 *   1. 三数取中：避免数据基本有序时退化到 O(n²)
 *   2. 数据量较小时改用插入排序（优化递归开销）
 */

// 对 [left, right] 区间做插入排序（用于小区间优化）
void insertionSort(vector<int>& arr, int left, int right) {
    for (int i = left + 1; i <= right; i++) {
        int key = arr[i];
        int j = i - 1;
        while (j >= left && arr[j] > key) {
            arr[j + 1] = arr[j];
            j--;
        }
        arr[j + 1] = key;
    }
}

// 三数取中：返回 left、mid、right 三者的中位数下标
int medianOfThree(vector<int>& arr, int left, int right) {
    int mid = left + (right - left) / 2;
    if (arr[left] > arr[mid]) swap(arr[left], arr[mid]);
    if (arr[left] > arr[right]) swap(arr[left], arr[right]);
    if (arr[mid] > arr[right]) swap(arr[mid], arr[right]);
    // 此时 arr[mid] 是中位数，将其换到倒数第二位便于分区
    swap(arr[mid], arr[right - 1]);
    return arr[right - 1];
}

// 分区函数（Hoare 思想的改进版：挖坑法 + 三数取中）
int partition(vector<int>& arr, int left, int right) {
    int pivot = medianOfThree(arr, left, right);

    int i = left;        // 左指针
    int j = right - 1;   // 右指针（right-1 已放基准）

    while (true) {
        while (arr[++i] < pivot);  // 从左往右找比基准大的
        while (arr[--j] > pivot);  // 从右往左找比基准小的
        if (i < j) {
            swap(arr[i], arr[j]);
        } else {
            break;
        }
    }
    // 将基准放到正确位置
    swap(arr[i], arr[right - 1]);
    return i;  // 返回基准最终下标
}

// 快速排序主体
void quickSort(vector<int>& arr, int left, int right) {
    // 区间大小小于阈值时用插入排序，减少递归深度
    if (right - left + 1 <= 10) {
        insertionSort(arr, left, right);
        return;
    }
    if (left < right) {
        int pivotIndex = partition(arr, left, right);
        quickSort(arr, left, pivotIndex - 1);
        quickSort(arr, pivotIndex + 1, right);
    }
}

// 对外接口
void quickSort(vector<int>& arr) {
    if (arr.empty()) return;
    quickSort(arr, 0, arr.size() - 1);
}

// 打印数组
void printArray(const vector<int>& arr) {
    for (int num : arr) {
        cout << num << " ";
    }
    cout << endl;
}

int main() {
    srand(static_cast<unsigned>(time(nullptr)));

    // 生成随机测试数据
    const int N = 20;
    vector<int> arr(N);
    for (int i = 0; i < N; i++) {
        arr[i] = rand() % 100;
    }

    cout << "排序前：";
    printArray(arr);

    quickSort(arr);

    cout << "排序后：";
    printArray(arr);

    // 验证排序结果
    bool sorted = is_sorted(arr.begin(), arr.end());
    cout << (sorted ? "✅ 排序正确！" : "❌ 排序有误！") << endl;

    return 0;
}
