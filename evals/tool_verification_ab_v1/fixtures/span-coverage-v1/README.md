修复半开区间调用链merge_spans(spans)与coverage(spans)。spans仅list/tuple；每项为长度2的list/tuple，两个端点必须真正int（bool无效），允许负数；start>end或任意非法输入均ValueError，start==end忽略。merge_spans返回按start排序、合并所有重叠或首尾相接区间的list[tuple]；不得修改输入。coverage必须调用merge_spans后返回并集总长度，不能对原区间直接求和；空输入或全空区间返回0。

python -m unittest discover -s tests -v
