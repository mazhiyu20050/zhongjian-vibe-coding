import unittest
from advice_tendencies import validate_options, validate_tendency


class TendencyTests(unittest.TestCase):
    def setUp(self):
        self.options=['沟通核实','调整自己','保持距离']
        self.weights=[{'option':s,'percent':p} for s,p in zip(self.options,[60,30,10])]

    def test_options_are_question_specific_and_unique(self):
        self.assertEqual(validate_options(['继续尝试','调整目标']),['继续尝试','调整目标'])
        for options in ([],['一种'],['重复','重复'],['过长选项'*4,'另一项']):
            with self.assertRaises(ValueError):validate_options(options)

    def test_ui_options_are_short_without_cutting_an_existing_sentence(self):
        self.assertEqual(validate_options(['核实','调整','远离']),['核实','调整','远离'])
        with self.assertRaises(ValueError):
            validate_options(['先核实对方所指事实','调整自己'])

    def test_weights_have_same_order_and_total(self):
        self.assertEqual(validate_tendency(self.weights[::-1],self.options,'先核实具体事实。'),self.weights)

    def test_bad_totals_and_false_precision_are_rejected(self):
        for values in ([50,30,10],[61,29,10],[-10,90,20],[True,30,69]):
            with self.subTest(values=values),self.assertRaises(ValueError):
                validate_tendency([{'option':s,'percent':p} for s,p in zip(self.options,values)],self.options,'一句依据。')

    def test_missing_information_is_not_filled_with_fake_numbers(self):
        self.assertIsNone(validate_tendency(None,self.options,'尚未知道对方指出了什么具体行为。'))

    def test_wrong_options_and_missing_reasons_are_rejected(self):
        wrong=[dict(item) for item in self.weights];wrong[0]['option']='绝对正确'
        with self.assertRaises(ValueError):validate_tendency(wrong,self.options,'理由。')
        with self.assertRaises(ValueError):validate_tendency(self.weights,self.options,'')


if __name__=='__main__':unittest.main()
